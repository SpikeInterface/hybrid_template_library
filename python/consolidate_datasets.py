from pathlib import Path
from argparse import ArgumentParser

import boto3
import pandas as pd
import zarr
import numpy as np
from tqdm.auto import tqdm

from spikeinterface.core import Templates

parser = ArgumentParser(description="Consolidate datasets from spikeinterface template database")

parser.add_argument("--dry-run", action="store_true", help="Dry run (no upload)")
parser.add_argument("--verbose", action="store_true", help="Print additional information during processing")


def list_zarr_directories(bucket_name, boto_client=None) -> list[str]:
    """Lists top-level Zarr directory keys in an S3 bucket.

    Parameters
    ----------
    bucket_name : str
        The name of the S3 bucket to search.
    boto_client : boto3.client, optional
        An existing Boto3 S3 client. If not provided, a new client will be created.

    Returns
    -------
    zarr_directories : list
        A list of strings representing the full S3 keys (paths) of top-level Zarr directories
        found in the bucket.
    """

    boto_client = boto_client or boto3.client("s3")
    zarr_directories = set()

    paginator = boto_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket_name, Delimiter="/"):
        for prefix in page.get("CommonPrefixes", []):
            key = prefix["Prefix"]
            if key.endswith(".zarr/"):
                zarr_directories.add(key.rstrip("/"))

    return list(zarr_directories)


def consolidate_datasets(dry_run: bool = False, verbose: bool = False):
    """Consolidates data from Zarr datasets within an S3 bucket.

    Parameters
    ----------
    dry_run : bool, optional
        If True, do not upload the consolidated data to S3. Defaults to False.
    verbose : bool, optional
        If True, print additional information during processing. Defaults to False.

    Returns
    -------
    pandas.DataFrame
        A DataFrame containing the consolidated data from all Zarr datasets.

    Raises
    ------
    FileNotFoundError
        If no Zarr datasets are found in the specified bucket.
    """

    bucket = "spikeinterface-template-database"
    boto_client = boto3.client("s3")

    # Get list of Zarr directories, excluding test datasets
    zarr_datasets = list_zarr_directories(bucket_name=bucket, boto_client=boto_client)
    datasets_to_avoid = ["test_templates.zarr"]
    zarr_datasets = [d for d in zarr_datasets if d not in datasets_to_avoid]
    zarr_datasets = sorted(zarr_datasets)

    if not zarr_datasets:
        raise FileNotFoundError(f"No Zarr datasets found in bucket: {bucket}")
    if verbose:
        print(f"Found {len(zarr_datasets)} datasets to consolidate\n")

    # Initialize list to collect DataFrames for each dataset
    all_dataframes = []
    desc = "Processing Zarr datasets"
    for dataset in tqdm(zarr_datasets, desc=desc, unit=" datasets processed", disable=not verbose):
        if verbose:
            print(f"Processing dataset: {dataset}")
        zarr_path = f"s3://{bucket}/{dataset}"
        zarr_group = zarr.open_consolidated(zarr_path, storage_options=dict(anon=True))
        templates = Templates.from_zarr_group(zarr_group)

        # Extract data efficiently using NumPy arrays
        num_units = templates.num_units
        probe_attributes = zarr_group["probe"]["annotations"].attrs.asdict()
        template_indices = np.arange(num_units)
        default_brain_area = ["unknown"] * num_units
        brain_areas = zarr_group.get("brain_area", default_brain_area)
        channel_depths = templates.get_channel_locations()[:, 1]
        spikes_per_unit = zarr_group["spikes_per_unit"][:]
        best_channel_indices = zarr_group["best_channel_index"][:]

        depth_best_channel = channel_depths[best_channel_indices]
        peak_to_peak_best_channel = zarr_group["peak_to_peak"][template_indices, best_channel_indices]
        if "channel_noise_levels" not in zarr_group:
            noise_best_channel = np.nan * np.zeros(num_units)
            signal_to_noise_ratio_best_channel = np.nan * np.zeros(num_units)
        else:
            noise_best_channel = zarr_group["channel_noise_levels"][best_channel_indices]
            signal_to_noise_ratio_best_channel = peak_to_peak_best_channel / noise_best_channel

        new_entry = pd.DataFrame(
            {
                "probe": [probe_attributes["model_name"]] * num_units,
                "probe_manufacturer": [probe_attributes["manufacturer"]] * num_units,
                "brain_area": brain_areas,
                "depth_along_probe": depth_best_channel,
                "amplitude_uv": peak_to_peak_best_channel,
                "noise_level_uv": noise_best_channel,
                "signal_to_noise_ratio": signal_to_noise_ratio_best_channel,
                "template_index": template_indices,
                "best_channel_index": best_channel_indices,
                "spikes_per_unit": spikes_per_unit,
                "dataset": [dataset] * num_units,
                "dataset_path": [zarr_path] * num_units,
            }
        )

        all_dataframes.append(new_entry)

    # Concatenate all DataFrames into a single DataFrame
    templates_df = pd.concat(all_dataframes, ignore_index=True)

    templates_file_name = "templates.csv"
    local_template_folder = Path("./build/")
    local_template_info_file_path = local_template_folder / templates_file_name
    templates_df.to_csv(local_template_info_file_path, index=False)

    # Upload to S3
    if dry_run:
        print("Dry run: skipping upload to S3")
    else:
        boto_client.upload_file(
            Filename=local_template_info_file_path,
            Bucket=bucket,
            Key=templates_file_name,
        )

    if verbose:
        print(templates_df)

    return templates_df


if __name__ == "__main__":
    params = parser.parse_args()
    dry_run = params.dry_run
    verbose = params.verbose
    templates_df = consolidate_datasets(dry_run=dry_run, verbose=verbose)
