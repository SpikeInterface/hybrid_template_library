import numpy as np
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

import s3fs
import zarr
import numcodecs

from one.api import ONE
import os


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


client = DandiAPIClient.for_dandi_instance("dandi")

dandiset_id = "000409"
dandiset = client.get_dandiset(dandiset_id)

valid_dandiset_path = lambda path: path.endswith(".nwb") and "ecephys" in path
dandiset_paths_with_ecephys = [
    asset.path for asset in dandiset.get_assets() if valid_dandiset_path(asset.path)
]
dandiset_paths_with_ecephys.sort()
dandiset_paths_with_ecephys = [
    path for path in dandiset_paths_with_ecephys if "KS" in path
]


ONE.setup(base_url="https://openalyx.internationalbrainlab.org", silent=True)
one_instance = ONE(password="international")

for asset_path in dandiset_paths_with_ecephys[1:]:
    # asset_path = "sub-KS051/sub-KS051_ses-0a018f12-ee06-4b11-97aa-bbbff5448e9f_behavior+ecephys+image.nwb"
    print("-------------------")
    print(asset_path)

    recording_asset = dandiset.get_asset_by_path(path=asset_path)
    url = recording_asset.get_content_url(follow_redirects=True, strip_query=True)
    file_path = url

    electrical_series_paths = (
        NwbRecordingExtractor.fetch_available_electrical_series_paths(
            file_path=file_path, stream_mode="remfile"
        )
    )
    electrical_series_paths_ap = [
        path for path in electrical_series_paths if "Ap" in path.split("/")[-1]
    ]
    for electrical_series_path in electrical_series_paths_ap:
        print(electrical_series_path)

        recording = NwbRecordingExtractor(
            file_path=file_path,
            stream_mode="remfile",
            electrical_series_path=electrical_series_path,
        )
        session_id = recording._file["general"]["session_id"][()].decode()
        eid = session_id.split("-chunking")[0]  # eid : experiment id
        pids, probes = one_instance.eid2pid(eid)
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

        minutes = 60
        samples_before_end = int(minutes * 60.0 * sampling_frequency_recording)

        start_frame_recording = num_samples - samples_before_end
        end_frame_recording = num_samples

        recording = recording.frame_slice(
            start_frame=start_frame_recording, end_frame=end_frame_recording
        )

        samples_before_end = int(minutes * 60.0 * sorting_sampling_frequency)
        start_frame_sorting = num_samples - samples_before_end
        end_frame_sorting = num_samples

        sorting_end = sorting.frame_slice(
            start_frame=start_frame_sorting, end_frame=end_frame_sorting
        )

        pre_processed_recording = common_reference(
            highpass_filter(
                phase_shift(astype(recording=recording, dtype="float32")), freq_min=1.0
            )
        )

        folder_path = "./pre_processed_recording"
        pre_processed_recording = pre_processed_recording.save_to_folder(
            folder=folder_path,
            overwrite=True,
            n_jobs=1,
            chunk_memory="1G",
            verbose=True,
            progress_bar=True,
        )

        analyzer = create_sorting_analyzer(
            sorting_end, pre_processed_recording, sparse=False, folder=f"analyzer_{eid}"
        )

        random_spike_parameters = {
            "method": "all",
        }

        template_extension_parameters = {
            "ms_before": 3.0,
            "ms_after": 5.0,
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

        analyzer.compute_several_extensions(
            extensions=extensions,
            n_jobs=3,
            verbose=True,
            progress_bar=True,
            chunk_memory="1G",
        )

        noise_level_extension = analyzer.get_extension("noise_levels")
        noise_level_data = noise_level_extension.get_data()

        templates_extension = analyzer.get_extension("templates")
        templates_extension_data = templates_extension.get_data(outputs="Templates")

        templates_extension = analyzer.get_extension("templates")
        templates_object = templates_extension.get_data(outputs="Templates")
        unit_ids = templates_object.unit_ids
        best_channels = find_channels_with_max_peak_to_peak_vectorized(
            templates_object.templates_array
        )

        templates_object.probe.model_name = probe_info[0]["model_name"]
        templates_object.probe.manufacturer = probe_info[0]["manufacturer"]
        templates_object.probe.serial_number = probe_info[0]["serial_number"]

        # AWS credentials
        aws_access_key_id = os.environ.get("AWS_ACCESS_KEY_ID")
        aws_secret_access_key = os.environ.get("AWS_SECRET_ACCESS_KEY")

        # Create a S3 file system object with explicit credentials
        s3_kwargs = dict(
            anon=False,
            key=aws_access_key_id,
            secret=aws_secret_access_key,
            client_kwargs={"region_name": "us-east-2"},
        )
        s3 = s3fs.S3FileSystem(**s3_kwargs)

        # Specify the S3 bucket and path
        path = asset_path.split("/")[-1]
        dataset_name = f"{dandiset_id}_{path}_{sorting_pid}"
        store = s3fs.S3Map(
            root=f"spikeinterface-template-database/{dataset_name}.zarr", s3=s3
        )

        zarr_group = zarr.group(store=store, overwrite=True)

        brain_area = sorting_end.get_property("brain_area")
        zarr_group.create_dataset(
            name="brain_area", data=brain_area, object_codec=numcodecs.VLenUTF8()
        )
        spikes_per_unit = sorting_end.count_num_spikes_per_unit(outputs="array")
        zarr_group.create_dataset(
            name="spikes_per_unit", data=spikes_per_unit, chunks=None, dtype="int32"
        )
        zarr_group.create_dataset(
            name="best_channels", data=best_channels, chunks=None, dtype="int32"
        )
        peak_to_peak = peak_to_peak_values = np.ptp(
            templates_extension_data.templates_array, axis=1
        )
        zarr_group.create_dataset(name="peak_to_peak", data=peak_to_peak)
        zarr_group.create_dataset(
            name="channe_noise_levels",
            data=noise_level_data,
            chunks=None,
            dtype="float32",
        )
        # Now you can create a Zarr array using this setore
        templates_extension_data.add_templates_to_zarr_group(zarr_group=zarr_group)
        zarr_group_s3 = zarr_group

        zarr.consolidate_metadata(zarr_group_s3.store)
