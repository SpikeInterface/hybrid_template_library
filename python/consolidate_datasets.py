import boto3
import pandas as pd
import zarr
import numpy as np
from argparse import ArgumentParser

from spikeinterface.core import Templates

parser = ArgumentParser(description="Consolidate datasets from spikeinterface template database")

parser.add_argument("--dry-run", action="store_true", help="Dry run (no upload)")
parser.add_argument("--no-skip-test", action="store_true", help="Skip test datasets")
parser.add_argument("--bucket", type=str, help="S3 bucket name", default="spikeinterface-template-database")


def list_bucket_objects(
    bucket: str,
    boto_client: boto3.client,
    prefix: str = "",
    include_substrings: str | list[str] | None = None,
    skip_substrings: str | list[str] | None = None,
):
    # get all objects for session from s3
    paginator = boto_client.get_paginator("list_objects_v2")
    pages = paginator.paginate(Prefix=prefix, Bucket=bucket)
    keys = []

    if include_substrings is not None:
        if isinstance(include_substrings, str):
            include_substrings = [include_substrings]
    if skip_substrings is not None:
        if isinstance(skip_substrings, str):
            skip_substrings = [skip_substrings]

    for page in pages:
        for item in page.get("Contents", []):
            key = item["Key"]
            if include_substrings is None and skip_substrings is None:
                keys.append(key)
            else:
                if skip_substrings is not None:
                    if any([s in key for s in skip_substrings]):
                        continue
                if include_substrings is not None:
                    if all([s in key for s in include_substrings]):
                        keys.append(key)
    return keys


def consolidate_datasets(
    dry_run: bool = False, skip_test_folder: bool = True, bucket="spikeinterface-template-database"
):
    ### Find datasets and create dataframe with consolidated data
    bc = boto3.client("s3")

    # Each dataset is stored in a zarr folder, so we look for the .zattrs files
    skip_substrings = ["test_templates"] if skip_test_folder else None
    keys = list_bucket_objects(bucket, boto_client=bc, include_substrings=".zattrs", skip_substrings=skip_substrings)
    datasets = [k.split("/")[0] for k in keys]
    print(f"Found {len(datasets)} datasets to consolidate\n")

    templates_df = None

    # Loop over datasets and extract relevant information
    for dataset in datasets:
        print(f"Processing dataset {dataset}")
        zarr_path = f"s3://{bucket}/{dataset}"
        zarr_group = zarr.open_consolidated(zarr_path, storage_options=dict(anon=True))

        templates = Templates.from_zarr_group(zarr_group)

        num_units = templates.num_units
        dataset_list = [dataset] * num_units
        dataset_path = [zarr_path] * num_units
        template_idxs = np.arange(num_units)
        best_channel_idxs = zarr_group.get("best_channels", None)
        brain_areas = zarr_group.get("brain_area", None)
        peak_to_peaks = zarr_group.get("peak_to_peak", None)
        spikes_per_units = zarr_group.get("spikes_per_unit", None)

        # TODO: get probe name from probe metadata

        channel_depths = templates.get_channel_locations()[:, 1]

        depths = np.zeros(num_units)
        amps = np.zeros(num_units)

        if best_channel_idxs is not None:
            best_channel_idxs = best_channel_idxs[:]
            for i, best_channel_idx in enumerate(best_channel_idxs):
                depths[i] = channel_depths[best_channel_idx]
                if peak_to_peaks is None:
                    amps[i] = np.ptp(templates.templates_array[i, :, best_channel_idx])
                else:
                    amps[i] = peak_to_peaks[i, best_channel_idx]
        else:
            depths = np.nan
            amps = np.nan
            best_channel_idxs = [-1] * num_units
            spikes_per_units = [-1] * num_units
        if brain_areas is not None:
            brain_areas = brain_areas[:]
        else:
            brain_areas = ["unknwown"] * num_units

        new_entry = pd.DataFrame(
            data={
                "dataset": dataset_list,
                "dataset_path": dataset_path,
                "probe": ["Neuropixels1.0"] * num_units,
                "template_index": template_idxs,
                "best_channel_id": best_channel_idxs,
                "brain_area": brain_areas,
                "depth_along_probe": depths,
                "amplitude_uv": amps,
                "spikes_per_unit": spikes_per_units,
            }
        )
        if templates_df is None:
            templates_df = new_entry
        else:
            templates_df = pd.concat([templates_df, new_entry])
        print(f"Added {num_units} units from dataset {dataset}")

    templates_df.reset_index(inplace=True)
    templates_df.to_csv("templates.csv", index=False)

    # Upload to S3
    if not dry_run:
        bc.upload_file("templates.csv", bucket, "templates.csv")
    else:
        print("Dry run, not uploading")
        print(templates_df)

    return templates_df


if __name__ == "__main__":
    params = parser.parse_args()
    DRY_RUN = params.dry_run
    SKIP_TEST = not params.no_skip_test
    templates_df = consolidate_datasets(dry_run=DRY_RUN, skip_test_folder=SKIP_TEST)
