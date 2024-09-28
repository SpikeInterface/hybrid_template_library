"""
This script constructs and uploads the templates from the International Brain Laboratory (IBL) datasets
available from DANDI (https://dandiarchive.org/dandiset/000409?search=IBL&pos=3). 

Templates are extracted by combining the raw data from the NWB files on DANDI with the spike trains form
the Alyx ONE database. Only the units that passed the IBL quality control are used.
To minimize the amount of drift in the templates, only the last 30 minutes of the recording are used. 
The raw recordings are pre-processed with a high-pass filter and a common median reference prior to 
template extraction. Units with less than 50 spikes are excluded from the template database.

Once the templates are constructed they are saved to a Zarr file which is then uploaded to 
"spikeinterface-template-database" bucket (hosted by CatalystNeuro).
"""

from pathlib import Path

import numpy as np
import s3fs
import zarr
import time
import os
import numcodecs

from dandi.dandiapi import DandiAPIClient

from spikeinterface.extractors import (
    NwbRecordingExtractor,
    IblSortingExtractor,
    IblRecordingExtractor,
)
from spikeinterface.core import create_sorting_analyzer
from spikeinterface.preprocessing import (
    astype,
    phase_shift,
    common_reference,
    highpass_filter,
)

from one.api import ONE

from consolidate_datasets import list_zarr_directories


def find_channels_with_max_peak_to_peak_vectorized(templates):
    """
    Find the channel indices with the maximum peak-to-peak value in each waveform template
    using a vectorized operation for improved performance.

    Parameters:
    templates (numpy.ndarray): The waveform templates, typically a 3D array (units x time x channels).

    Returns:
    numpy.ndarray: An array of indices of the channel with the maximum peak-to-peak value for each unit.
    """
    # Compute the peak-to-peak values along the time axis (axis=1) for each channel of each unit
    peak_to_peak_values = np.ptp(templates, axis=1)

    # Find the indices of the channel with the maximum peak-to-peak value for each unit
    best_channels = np.argmax(peak_to_peak_values, axis=1)

    return best_channels


# AWS credentials
aws_access_key_id = os.environ.get("AWS_ACCESS_KEY_ID")
aws_secret_access_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
bucket_name = "spikeinterface-template-database"
client_kwargs = {"region_name": "us-east-2"}

# Parameters
minutes_by_the_end = 30  # How many minutes in the end of the recording to use for templates
min_spikes_per_unit = 50
upload_data = True
overwite = False
verbose = True

# Test data
do_testing_data = False
test_path = "sub-KS051/sub-KS051_ses-0a018f12-ee06-4b11-97aa-bbbff5448e9f_behavior+ecephys+image.nwb"

ONE.setup(base_url="https://openalyx.internationalbrainlab.org", silent=True)
one_instance = ONE(password="international")

client = DandiAPIClient.for_dandi_instance("dandi")
dandiset_id = "000409"
dandiset = client.get_dandiset(dandiset_id)

has_ecephy_data = lambda path: path.endswith(".nwb") and "ecephys" in path
dandiset_paths = [asset.path for asset in dandiset.get_assets() if has_ecephy_data(asset.path)]
dandiset_paths.sort()
dandiset_paths = [path for path in dandiset_paths if "KS" in path]

if do_testing_data:
    dandiset_paths = [test_path]

# Load already processed datasets
zarr_datasets = list_zarr_directories(bucket_name=bucket_name)
if verbose:
    print(f"Found {len(zarr_datasets)} datasets already processed")

dandiset_paths = np.random.choice(dandiset_paths, size=len(dandiset_paths), replace=False)
for asset_path in dandiset_paths:
    if verbose:
        print("----------------------------------------------------------")
        print("----------------------------------------------------------")
        print("----------------------------------------------------------")

        print(asset_path)

    recording_asset = dandiset.get_asset_by_path(path=asset_path)
    url = recording_asset.get_content_url(follow_redirects=True, strip_query=True)
    file_path = url

    electrical_series_paths = NwbRecordingExtractor.fetch_available_electrical_series_paths(
        file_path=file_path, stream_mode="remfile"
    )
    electrical_series_paths_ap = [path for path in electrical_series_paths if "Ap" in path.split("/")[-1]]
    for electrical_series_path in electrical_series_paths_ap:
        print(f"{electrical_series_path=}")

        recording = NwbRecordingExtractor(
            file_path=file_path,
            stream_mode="remfile",
            electrical_series_path=electrical_series_path,
        )

        if verbose:
            print("Recording")
            print(recording)

        session_id = recording._file["general"]["session_id"][()].decode()
        eid = session_id.split("-chunking")[0]  # eid : experiment id
        pids, probes = one_instance.eid2pid(eid)
        if verbose:
            print("pids", pids)
            print("probes", probes)

        if len(probes) > 1:
            probe_number = electrical_series_path.split("Ap")[-1]
            for pid, probe in zip(pids, probes):
                probe_number_in_pid = probe[-2:]
                if probe_number_in_pid == probe_number:
                    sorting_pid = pid
                    break

        else:
            sorting_pid = pids[0]
            probe_number = "00"

        if do_testing_data:
            dataset_name = "test_templates.zarr"
        else:
            dandi_name = asset_path.split("/")[-1].split(".")[0]
            dataset_name = f"{dandiset_id}_{dandi_name}_{sorting_pid}.zarr"

        if dataset_name in zarr_datasets and not overwite:
            if verbose:
                print(f"Dataset {dataset_name} already processed, skipping")
            continue

        sorting = IblSortingExtractor(
            pid=sorting_pid,
            one=one_instance,
            good_clusters_only=True,
        )

        # streams = IblRecordingExtractor.get_stream_names(eid=eid, one=one_instance)
        stream_name = f"probe{probe_number}.ap"
        ibl_recording = IblRecordingExtractor(
            eid=eid,
            stream_name=stream_name,
            one=one_instance,
        )
        probe_info = ibl_recording.get_annotation("probes_info")

        sampling_frequency_recording = recording.sampling_frequency
        sorting_sampling_frequency = sorting.sampling_frequency
        num_samples = recording.get_num_samples()

        samples_before_end = int(minutes_by_the_end * 60.0 * sampling_frequency_recording)

        start_frame_recording = num_samples - samples_before_end
        end_frame_recording = num_samples

        recording = recording.frame_slice(start_frame=start_frame_recording, end_frame=end_frame_recording)
        samples_before_end = int(minutes_by_the_end * 60.0 * sorting_sampling_frequency)
        start_frame_sorting = num_samples - samples_before_end
        end_frame_sorting = num_samples

        sorting_end = sorting.frame_slice(start_frame=start_frame_sorting, end_frame=end_frame_sorting)

        spikes_per_unit = sorting_end.count_num_spikes_per_unit(outputs="array")
        unit_indices_to_keep = np.where(spikes_per_unit >= min_spikes_per_unit)[0]
        sorting_end = sorting_end.select_units(sorting_end.unit_ids[unit_indices_to_keep])

        # NWB Streaming is not working well with parallel pre=processing so we ave
        folder_path = Path.cwd() / "build" / "local_copy"
        folder_path.mkdir(exist_ok=True, parents=True)

        if verbose:
            print("Saving Recording")
            print(recording)
            start_time = time.time()

        recording = recording.save_to_folder(
            folder=folder_path,
            overwrite=True,
            n_jobs=8,
            chunk_memory="1Gi",
            verbose=True,
            progress_bar=True,
        )

        if verbose:
            end_time = time.time()
            execution_time = end_time - start_time
            print(f"Execution time: {execution_time/60.0: 2.2f} minutes")

        pre_processed_recording = common_reference(
            highpass_filter(phase_shift(astype(recording=recording, dtype="float32")), freq_min=1.0)
        )

        analyzer = create_sorting_analyzer(sorting_end, pre_processed_recording, sparse=False, folder=f"analyzer_{eid}")

        random_spike_parameters = {
            "method": "all",
        }

        # Correct for round mismatches in the number of temporal samples in conversion from seconds to samples
        target_ms_before = 3.0
        target_ms_after = 5.0
        expected_fs = 30_000
        target_nbefore = int(target_ms_before / 1000 * expected_fs)
        target_nafter = int(target_ms_after / 1000 * expected_fs)
        ms_before_corrected = target_nbefore / recording.sampling_frequency * 1000
        ms_after_corrected = target_nafter / recording.sampling_frequency * 1000

        template_extension_parameters = {
            "ms_before": ms_before_corrected,
            "ms_after": ms_after_corrected,
            "operators": ["average"],
        }

        noise_level_parameters = {
            "chunk_size": 10_000,
            "num_chunks_per_segment": 20,
        }

        extensions = {
            "random_spikes": random_spike_parameters,
            "templates": template_extension_parameters,
            "noise_levels": noise_level_parameters,
        }

        if verbose:
            print("Computing extensions")
            start_time = time.time()

        analyzer.compute_several_extensions(
            extensions=extensions,
            n_jobs=8,
            verbose=True,
            progress_bar=True,
            chunk_memory="250Mi",
        )

        if verbose:
            end_time = time.time()
            execution_time = end_time - start_time
            print(f"Execution time: {execution_time/60.0: 2.2f} minutes")

        noise_level_extension = analyzer.get_extension("noise_levels")
        noise_level_data = noise_level_extension.get_data()

        templates_extension = analyzer.get_extension("templates")
        templates_extension_data = templates_extension.get_data(outputs="Templates")

        # Do a check for the expected shape of the templates
        number_of_units = sorting.get_num_units()
        number_of_temporal_samples = target_nbefore + target_nafter
        number_of_channels = pre_processed_recording.get_num_channels()
        expected_shape = (number_of_units, number_of_temporal_samples, number_of_channels)
        assert templates_extension_data.templates_array.shape == expected_shape

        # TODO: skip templates with 0 amplitude!
        # TODO: check for weird shapes
        templates_extension = analyzer.get_extension("templates")
        templates_object = templates_extension.get_data(outputs="Templates")
        unit_ids = templates_object.unit_ids
        best_channel_index = find_channels_with_max_peak_to_peak_vectorized(templates_object.templates_array)

        templates_object.probe.model_name = probe_info[0]["model_name"]
        templates_object.probe.manufacturer = probe_info[0]["manufacturer"]
        templates_object.probe.serial_number = probe_info[0]["serial_number"]

        if verbose:
            print("Saving data to Zarr")
            print(f"{dataset_name=}")

        if upload_data:
            # Create a S3 file system object with explicit credentials
            s3_kwargs = dict(
                anon=False, key=aws_access_key_id, secret=aws_secret_access_key, client_kwargs=client_kwargs
            )
            s3 = s3fs.S3FileSystem(**s3_kwargs)

            # Specify the S3 bucket and path
            s3_path = f"{bucket_name}/{dataset_name}"
            store = s3fs.S3Map(root=s3_path, s3=s3)
        else:
            folder_path = Path.cwd() / "build" / f"{dataset_name}"
            folder_path.mkdir(exist_ok=True, parents=True)
            store = zarr.DirectoryStore(str(folder_path))

        # Save results to Zarr
        zarr_group = zarr.group(store=store, overwrite=True)
        brain_area = sorting_end.get_property("brain_area")
        zarr_group.create_dataset(name="brain_area", data=brain_area, object_codec=numcodecs.VLenUTF8())
        spikes_per_unit = sorting_end.count_num_spikes_per_unit(outputs="array")
        zarr_group.create_dataset(name="spikes_per_unit", data=spikes_per_unit, chunks=None, dtype="uint32")
        zarr_group.create_dataset(
            name="best_channel_index",
            data=best_channel_index,
            chunks=None,
            dtype="uint32",
        )
        peak_to_peak = np.ptp(templates_extension_data.templates_array, axis=1)
        zarr_group.create_dataset(name="peak_to_peak", data=peak_to_peak)
        zarr_group.create_dataset(
            name="channel_noise_levels",
            data=noise_level_data,
            chunks=None,
            dtype="float32",
        )
        # Now you can create a Zarr array using this store
        templates_extension_data.add_templates_to_zarr_group(zarr_group=zarr_group)
        zarr_group_s3 = zarr_group
        zarr.consolidate_metadata(zarr_group_s3.store)
