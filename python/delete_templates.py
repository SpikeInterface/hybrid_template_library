import boto3
import numpy as np
import zarr

from consolidate_datasets import list_zarr_directories


def delete_template_from_s3(bucket_name: str, template_key: str, boto_client: boto3.client = None) -> None:
    """Deletes a Zarr template (and its contents) from S3."""

    boto_client = boto_client or boto3.client("s3")

    # Delete all objects within the template directory (including nested directories)
    boto_client.delete_objects(
        Bucket=bucket_name,
        Delete={
            "Objects": [
                {"Key": obj["Key"]}
                for obj in boto_client.list_objects_v2(Bucket=bucket_name, Prefix=template_key).get("Contents", [])
            ]
        },
    )
    print(f"Deleted template: {template_key}")


def delete_templates_from_s3(
    bucket_name: str,
    template_keys: list[str],
    boto_client: boto3.client = None,
) -> None:
    """Deletes multiple Zarr templates from S3."""
    boto_client = boto_client or boto3.client("s3")
    for key in template_keys:
        delete_template_from_s3(bucket_name, key, boto_client=boto_client)


def delete_templates_too_few_spikes(min_spikes=50, dry_run=False, verbose=True):
    """
    This function will delete templates associated to spike trains with too few spikes.

    The initial database was in fact created without a minimum number of spikes per unit,
    so some units have very few spikes and possibly a noisy template.
    """
    import spikeinterface.generation as sgen

    templates_info = sgen.fetch_templates_database_info()
    templates_to_remove = templates_info.query(f"spikes_per_unit < {min_spikes}")

    if len(templates_to_remove) > 0:
        if verbose:
            print(
                f"Removing {len(templates_to_remove)}/{len(templates_info)} templates with less than {min_spikes} spikes"
            )
        datasets = np.unique(templates_to_remove["dataset"])

        for d_i, dataset in enumerate(datasets):
            if verbose:
                print(f"\tCleaning dataset {d_i + 1}/{len(datasets)}")
            templates_in_dataset = templates_to_remove.query(f"dataset == '{dataset}'")
            template_indices_to_remove = templates_in_dataset.template_index.values
            s3_path = templates_in_dataset.dataset_path.values[0]

            # to filter from the zarr dataset:
            datasets_to_filter = [
                "templates_array",
                "best_channel_index",
                "spikes_per_unit",
                "brain_area",
                "peak_to_peak",
                "unit_ids",
            ]

            # open zarr in append mode
            if dry_run:
                mode = "r"
            else:
                mode = "r+"
            zarr_root = zarr.open(s3_path, mode=mode)
            all_unit_indices = np.arange(len(zarr_root["unit_ids"]))
            n_original_units = len(all_unit_indices)
            unit_indices_to_keep = np.delete(all_unit_indices, template_indices_to_remove)
            n_units_to_keep = len(unit_indices_to_keep)
            if verbose:
                print(f"\tRemoving {n_original_units - n_units_to_keep} templates from {n_original_units}")
            for dset in datasets_to_filter:
                dataset_original = zarr_root[dset]
                if len(dataset_original) == n_units_to_keep:
                    print(f"\t\tDataset: {dset} - shape: {dataset_original.shape} - already updated")
                    continue
                dataset_filtered = dataset_original[unit_indices_to_keep]
                if not dry_run:
                    if verbose:
                        print(f"\t\tUpdating: {dset} - shape: {dataset_filtered.shape}")
                    if dataset_filtered.dtype.kind == "O":
                        dataset_filtered = dataset_filtered.astype(str)
                    zarr_root[dset] = dataset_filtered
                else:
                    if verbose:
                        print(f"\t\tDry run: {dset} - shape: {dataset_filtered.shape}")
            if not dry_run:
                zarr.consolidate_metadata(zarr_root.store)


def restore_noise_levels_ibl(datasets, one=None, dry_run=False, verbose=True):
    """
    This function will restore noise levels for IBL datasets.
    """
    import spikeinterface as si
    import spikeinterface.extractors as se
    import spikeinterface.generation as sgen

    for dataset in datasets:
        if verbose:
            print(f"Processing dataset: {dataset}")
        pid = dataset.split("_")[-1][:-5]
        dataset_path = f"s3://spikeinterface-template-database/{dataset}"
        recording = se.read_ibl_recording(pid=pid, load_sync_channel=False, stream_type="ap", one=one)

        default_params = si.get_default_analyzer_extension_params("noise_levels")
        if verbose:
            print(f"\tComputing noise levels")
        noise_levels = si.get_noise_levels(recording, return_scaled=True, **default_params)

        if dry_run:
            mode = "r"
        else:
            mode = "r+"
        zarr_root = zarr.open(dataset_path, mode=mode)
        if not dry_run:
            if verbose:
                print(f"\tRestoring noise levels")
            zarr_root["channel_noise_levels"] = noise_levels
            zarr.consolidate_metadata(zarr_root.store)
        else:
            if verbose:
                print(f"\tCurrent shape: {zarr_root['channel_noise_levels'].shape}")
                print(f"\tDry run: would restore noise levels: {noise_levels.shape}")


def delete_templates_with_num_samples(dry_run=False):
    """
    This function will delete templates with number of samples,
    which were not corrected for in the initial database.
    """
    bucket = "spikeinterface-template-database"
    boto_client = boto3.client("s3")
    verbose = True

    templates_to_erase_from_bucket = [
        "000409_sub-KS084_ses-1b715600-0cbc-442c-bd00-5b0ac2865de1_behavior+ecephys+image_bbe6ebc1-d32f-42dd-a89c-211226737deb.zarr",
        "000409_sub-KS086_ses-e45481fa-be22-4365-972c-e7404ed8ab5a_behavior+ecephys+image_f2a098e7-a67e-4125-92d8-36fc6b606c45.zarr",
        "000409_sub-KS091_ses-196a2adf-ff83-49b2-823a-33f990049c2e_behavior+ecephys+image_0259543e-1ca3-48e7-95c9-53f9e4c9bfcc.zarr",
        "000409_sub-KS091_ses-78b4fff5-c5ec-44d9-b5f9-d59493063f00_behavior+ecephys+image_19c5b0d5-a255-47ff-9f8d-639e634a7b61.zarr",
        "000409_sub-KS094_ses-6b0b5d24-bcda-4053-a59c-beaa1fe03b8f_behavior+ecephys+image_3282a590-8688-44fc-9811-cdf8b80d9a80.zarr",
        "000409_sub-KS094_ses-752456f3-9f47-4fbf-bd44-9d131c0f41aa_behavior+ecephys+image_100433fa-2c59-4432-8295-aa27657fe3fb.zarr",
        "000409_sub-KS094_ses-c8d46ee6-eb68-4535-8756-7c9aa32f10e4_behavior+ecephys+image_49a86b2e-3db4-42f2-8da8-7ebb7e482c70.zarr",
        "000409_sub-KS096_ses-1b9e349e-93f2-41cc-a4b5-b212d7ddc8df_behavior+ecephys+image_1c4e2ebd-59da-4527-9700-b4b2dad6dfb2.zarr",
        "000409_sub-KS096_ses-8928f98a-b411-497e-aa4b-aa752434686d_behavior+ecephys+image_d7ec0892-0a6c-4f4f-9d8f-72083692af5c.zarr",
        "000409_sub-KS096_ses-a2701b93-d8e1-47e9-a819-f1063046f3e7_behavior+ecephys+image_f336f6a4-f693-4b88-b12c-c5cf0785b061.zarr",
        "000409_sub-KS096_ses-f819d499-8bf7-4da0-a431-15377a8319d5_behavior+ecephys+image_4ea45238-55b1-4d54-ba92-efa47feb9f57.zarr",
    ]
    existing_templates = list_zarr_directories(bucket, boto_client=boto_client)
    templates_to_erase_from_bucket = [
        template for template in templates_to_erase_from_bucket if template in existing_templates
    ]
    if dry_run:
        if verbose:
            print(f"Would erase {len(templates_to_erase_from_bucket)} templates from bucket: {bucket}")
    else:
        if verbose:
            print(f"Erasing {len(templates_to_erase_from_bucket)} templates from bucket: {bucket}")
        delete_templates_from_s3(bucket, templates_to_erase_from_bucket, boto_client=boto_client)
