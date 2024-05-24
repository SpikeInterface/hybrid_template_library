import numpy as np
import s3fs
import zarr
import numcodecs
import os


from dandi.dandiapi import DandiAPIClient
from spikeinterface.extractors import NwbRecordingExtractor, IblSortingExtractor
from spikeinterface.extractors import IblRecordingExtractor

from one.api import ONE
from spikeinterface.preprocessing import (
    astype,
    phase_shift,
    common_reference,
    highpass_filter,
)
from spikeinterface.core import create_sorting_analyzer

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


for asset_path in dandiset_paths_with_ecephys:

    recording_asset = dandiset.get_asset_by_path(path=asset_path)
    url = recording_asset.get_content_url(follow_redirects=True, strip_query=True)
    file_path = url

    electrical_series_path = "acquisition/ElectricalSeriesAp00"
    recording = NwbRecordingExtractor(
        file_path=file_path,
        stream_mode="remfile",
        electrical_series_path=electrical_series_path,
    )
    session_id = recording._file["general"]["session_id"][()].decode()
    eid = session_id.split("-chunking")[0]  # eid : experiment id

    ONE.setup(base_url="https://openalyx.internationalbrainlab.org", silent=True)
    one_instance = ONE(password="international")

    pids, probes = one_instance.eid2pid(eid)

    # Let's select the probe
    probe_number = electrical_series_path.split("Ap")[-1]

    sorting_pid = None
    for pid, probe in zip(pids, probes):
        probe_number_in_pid = probe[-2:]
        if probe_number_in_pid == probe_number:
            sorting_pid = pid
            break

    sorting = IblSortingExtractor(
        pid=sorting_pid, one=one_instance, good_clusters_only=True
    )



    ibl_recording = IblRecordingExtractor(pid=pid, stream_name=f"probe{probe_number}.ap" )  
    probe_info = ibl_recording.get_annotation("probes_info")
    
    folder_path = "./nwb_recording/"
    recording_cache = recording.save_to_folder(
        folder=folder_path, overwrite=True, n_jobs=-1, chunk_memory="5G"
    )

    pre_processed_recording = common_reference(
        highpass_filter(
            phase_shift(astype(recording=recording_cache, dtype="float32")),
            freq_min=1.0,
        )
    )

    sampling_frequency_recording = pre_processed_recording.sampling_frequency
    sorting_sampling_frequency = sorting.sampling_frequency
    num_samples = pre_processed_recording.get_num_samples()

    # Take the last 60 minutes of the recording
    minutes = 60
    samples_before_end = int(minutes * 60.0 * sampling_frequency_recording)

    start_frame_recording = num_samples - samples_before_end
    end_frame_recording = num_samples

    recording_end = pre_processed_recording.frame_slice(
        start_frame=start_frame_recording, end_frame=end_frame_recording
    )

    samples_before_end = int(minutes * 60.0 * sorting_sampling_frequency)
    start_frame_sorting = num_samples - samples_before_end
    end_frame_sorting = num_samples

    sorting_end = sorting.frame_slice(
        start_frame=start_frame_sorting, end_frame=end_frame_sorting
    )

    analyzer = create_sorting_analyzer(
        sorting_end, recording_end, sparse=False, folder=f"analyzer_{eid}"
    )

    random_spike_parameters = {
        "method": "all",
    }

    template_extension_parameters = {
        "ms_before": 3.0,
        "ms_after": 5.0,
        "operators": ["average"],
    }

    extensions = {
        "random_spikes": random_spike_parameters,
        "templates": template_extension_parameters,
    }

    analyzer.compute_several_extensions(
        extensions=extensions,
        n_jobs=-1,
        progress_bar=True,
    )




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


    templates_extension = analyzer.get_extension("templates")
    templates_object = templates_extension.get_data(outputs="Templates")
    
    # Set probe info
    templates_object.probe.model_name = probe_info[0]["model_name"]
    templates_object.probe.manufacturer = probe_info[0]["manufacturer"]
    templates_object.probe.serial_number = probe_info[0]["serial_number"]

    
    unit_ids = templates_object.unit_ids
    best_channels = find_channels_with_max_peak_to_peak_vectorized(templates_object.templates_array)


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
    dataset_name = f"{dandiset_id}_{path}_{sorting_pid}.zarr"
    store = s3fs.S3Map(root=f"spikeinterface-template-database/{dataset_name}", s3=s3)

    zarr_group = zarr.group(store=store, overwrite=True)

    brain_area = sorting_end.get_property("brain_area")
    zarr_group.create_dataset(name="brain_area", data=brain_area, object_codec=numcodecs.VLenUTF8())
    spikes_per_unit = sorting_end.count_num_spikes_per_unit(outputs="array")
    zarr_group.create_dataset(name="spikes_per_unit", data=spikes_per_unit, chunks=None, dtype="int32")
    zarr_group.create_dataset(name="best_channels", data=best_channels, chunks=None, dtype="int32")
    peak_to_peak = peak_to_peak_values = np.ptp(templates_object.templates_array, axis=1)
    zarr_group.create_dataset(name="peak_to_peak", data=peak_to_peak)
    # Now you can create a Zarr array using this setore
    templates_object.add_templates_to_zarr_group(zarr_group=zarr_group)
    
    
    zarr.consolidate_metadata(zarr_group.store)
