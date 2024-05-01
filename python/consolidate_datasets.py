import boto3
import pandas as pd
import zarr
import numpy as np

from spikeinterface.core import Templates

REGION_NAME = 'us-east-2'
HYBRID_BUCKET = "spikeinterface-template-database"


def list_bucket_objects(
    bucket : str,
    boto_client : boto3.client,
    prefix : str = "",
    include_substrings : str | list[str] | None = None,
    skip_substrings : str | list[str] | None = None
):
    # get all objects for session from s3
    paginator = boto_client.get_paginator('list_objects_v2')
    pages = paginator.paginate(Prefix=prefix, Bucket=bucket)
    keys = []

    if include_substrings is not None:
        if isinstance(include_substrings, str):
            include_substrings = [include_substrings]
    if skip_substrings is not None:
        if isinstance(skip_substrings, str):
            skip_substrings = [skip_substrings]

    for page in pages:
        for item in page.get('Contents', []):
            key = item['Key']
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


def consolidate_datasets():
    ### Find datasets and create dataframe with consolidated data
    bc = boto3.client('s3')

    # Each dataset is stored in a zarr folder, so we look for the .zattrs files
    keys = list_bucket_objects(HYBRID_BUCKET, boto_client=bc, include_substrings=".zattrs")
    datasets = [k.split("/")[0] for k in keys]

    templates_df = pd.DataFrame(
        columns=["dataset", "template_index", "best_channel_id", "brain_area", "depth", "amplitude"]
    )

    # Loop over datasets and extract relevant information
    for dataset in datasets:
        print(f"Processing dataset {dataset}")
        zarr_path = f"s3://{HYBRID_BUCKET}/{dataset}"
        zarr_group = zarr.open_consolidated(zarr_path, storage_options=dict(anon=True))

        templates = Templates.from_zarr_group(zarr_group)

        num_units = templates.num_units
        dataset_list = [dataset] * num_units
        template_idxs = np.arange(num_units)
        best_channel_idxs = zarr_group.get("best_channels", None)
        brain_areas = zarr_group.get("brain_area", None)
        channel_depths = templates.get_channel_locations()[:, 1]

        depths = np.zeros(num_units)
        amps = np.zeros(num_units)

        if best_channels is not None:
            best_channels = best_channels[:]
            for i, best_channel_idx in enumerate(best_channels):
                depths[i] = channel_depths[best_channel_idx]
                amps[i] = np.ptp(templates.templates_array[i, :, best_channel_idx])
        else:
            depths = np.nan
            amps = np.nan
            best_channels = ["unknwown"] * num_units
        if brain_areas is not None:
            brain_areas = brain_areas[:]
        else:
            brain_areas = ["unknwown"] * num_units
        new_entry = pd.DataFrame(
            data={
                "dataset": dataset_list, 
                "template_index": template_idxs, 
                "best_channel_id": best_channels, 
                "brain_area": brain_areas, 
                "depth": depths,
                "amplitude": amps
            }
        )
        templates_df = pd.concat(
            [templates_df, new_entry]
        )

    templates_df.to_csv("templates.csv", index=False)

    # Upload to S3
    bc.upload_file("templates.csv", HYBRID_BUCKET, "templates.csv")


if __name__ == "__main__":
    consolidate_datasets()