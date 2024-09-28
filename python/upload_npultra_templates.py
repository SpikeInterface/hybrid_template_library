"""
This script constructs and uploads the templates from the Neuropixels Ultra dataset
form Steinmetz and Ye, 2022. The dataset is hosted on Figshare at https://doi.org/10.6084/m9.figshare.19493588.v2
The templates and relevant metadata are packaged into a `spikeinterface.Templates` and saved to a
Zarr file. The Zarr file is then uploaded to an S3 bucket hosted by CatalystNeuro for storage and sharing.

The s3 bucket "spikeinterface-template-database" is used by the SpikeInterface hybrid framework to construct hybrid
recordings.
"""
from pathlib import Path

import numpy as np
import s3fs
import zarr
import pandas as pd
import os
import numcodecs
import probeinterface as pi
import spikeinterface as si

min_spikes_per_unit = 50
upload_data = False

npultra_templates_path = Path("/home/alessio/Documents/Data/Templates/NPUltraWaveforms/")
dataset_name = "steinmetz_ye_np_ultra_2022_figshare19493588v2.zarr"

# AWS credentials
aws_access_key_id = os.environ.get("AWS_ACCESS_KEY_ID")
aws_secret_access_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
bucket_name = "spikeinterface-template-database"
client_kwargs = {"region_name": "us-east-2"}

# Load the templates and the required metadata
xpos = np.load(npultra_templates_path / "channels.xcoords.npy")
ypos = np.load(npultra_templates_path / "channels.ycoords.npy")

channel_locations = np.squeeze([xpos, ypos]).T

templates_array = np.load(npultra_templates_path / "clusters.waveforms.npy")
spike_clusters = np.load(npultra_templates_path / "spikes.clusters.npy")

brain_area = pd.read_csv(npultra_templates_path / "clusters.acronym.tsv", sep="\t")
brain_area_acronym = brain_area["acronym"].values

# Instantiate Probe
probe = pi.Probe(ndim=2)
probe.set_contacts(positions=channel_locations, shapes="square", shape_params={"width": 5})
probe.model_name = "Neuropixels Ultra"
probe.manufacturer = "IMEC"

# Unit ids and properties
unit_ids, spikes_per_unit = np.unique(spike_clusters, return_counts=True)
unit_ids_enough_spikes = spikes_per_unit >= min_spikes_per_unit
unit_ids = unit_ids[unit_ids_enough_spikes]
spikes_per_unit = spikes_per_unit[unit_ids_enough_spikes]

# sort the units by unit_id
sort_unit_indices = np.argsort(unit_ids)
unit_itd = unit_ids[sort_unit_indices]
spikes_per_unit = spikes_per_unit[sort_unit_indices]
brain_area_acronym = brain_area_acronym[sort_unit_indices]

# Create Templates object
nbefore = 40
sampling_frequency = 30000

templates_ultra = si.Templates(
    templates_array=templates_array,
    sampling_frequency=sampling_frequency,
    nbefore=nbefore,
    unit_ids=unit_ids,
    probe=probe,
    is_scaled=True
)

best_channel_index = si.get_template_extremum_channel(templates_ultra, mode="peak_to_peak", outputs="index")
best_channel_index = list(best_channel_index.values())

if upload_data:
    # Create a S3 file system object with explicit credentials
    s3_kwargs = dict(anon=False, key=aws_access_key_id, secret=aws_secret_access_key, client_kwargs=client_kwargs)
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
zarr_group.create_dataset(name="brain_area", data=brain_area, object_codec=numcodecs.VLenUTF8())
zarr_group.create_dataset(name="spikes_per_unit", data=spikes_per_unit, chunks=None, dtype="uint32")
zarr_group.create_dataset(
    name="best_channel_index",
    data=best_channel_index,
    chunks=None,
    dtype="uint32",
)
peak_to_peak = np.ptp(templates_array, axis=1)
zarr_group.create_dataset(name="peak_to_peak", data=peak_to_peak)

# Now you can create a Zarr array using this store
templates_ultra.add_templates_to_zarr_group(zarr_group=zarr_group)
zarr_group_s3 = zarr_group
zarr.consolidate_metadata(zarr_group_s3.store)
