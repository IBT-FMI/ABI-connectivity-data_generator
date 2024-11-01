# ABI Connectivity Data

Script to download and prepare connectivity data from the Allen Mouse Brain data portal [ABI-connectivity](http://connectivity.brain-map.org/) [[1][1]].
This script will query the database, download available data, convert it from the nrrd format to NIfTI, and register it to a standard space (DSURQEC, as seen in the relevant [mouse brain preprocessing article](https://www.sciencedirect.com/science/article/pii/S1053811921006625)).

# ABI Connectivity Data Package Releases

Current recommended release in bold typeface:

* **[ABI-connectivity-data-0.2.tar.xz](http://resources.chymera.eu/distfiles/ABI-connectivity-data-0.2.tar.xz)** \[[SHA512 checksum](http://resources.chymera.eu/distfiles/ABI-connectivity-data-0.2.sha512)\]
* [ABI-connectivity-data-0.1.tar.xz](http://resources.chymera.eu/distfiles/ABI-connectivity-data-0.1.tar.xz) \[[SHA512 checksum](http://resources.chymera.eu/distfiles/ABI-connectivity-data-0.1.sha512)\]

# Citation Notice

Citation guidelines for use of the Allen mouse brain atlas can be found at: https://alleninstitute.org/legal/citation-policy/


# Usage

In order to create a new version of the ABI-connectivity data package, simply navigate to the root directory of this repository and run:

```
python abi_connectivity.py -v 0.5 -x 200
```

This will create the archive with the newest files at 200um resolution fetched from upstream and processed according to the instructions standardized in this package.
The version suffix will be `0.5` (as per the `-v 0.5` parameter).

To create the ABI-connectivity-dataHD archives, run:

```
python abi_connectivity.py -v 0.5 -x 40
```
This will create the archives with the newest files at 40um resolution.

[1]: https://www.nature.com/articles/nature13186
