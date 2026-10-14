# Austrian Power Grid Model

This project constructs a model of the Austrian power grid using data from [OpenStreetMap (OSM)](https://www.openstreetmap.org/), collected using the [Get OSM data](gitlab.sba-research.org/eris/get-osm-data) repository. It is designed to be used in conjunction with the [Nurzu Load Flow Simulation](https://gitlab.sba-research.org/eris/nurzu-load-flow-simulation) repository, which consumes the `Model` object produced here to simulate electrical power flow.

This (along with [Nurzu Load Flow Simulation](https://gitlab.sba-research.org/eris/nurzu-load-flow-simulation) and [Get OSM data](gitlab.sba-research.org/eris/get-osm-data)) is part of a refactored and modularized successor to the now deprecated [nurzu-load-flow-analysis](https://gitlab.sba-research.org/johanna/nurzu-load-flow-analysis) repository.

## Overview

- Builds a model of Austria’s electric grid
- Uses OSM data with manual corrections
- Exports:
  - A model for simulation
  - Optional GeoJSON and graph visualizations
  - Supplementary CSV data for debugging or analysis


## Results

All output files are written to the `export/` directory:

- A json version of a `Model` object containing the full model
- Optional exports:
  - a GeoJSON file for geographic visualization (e.g. with geojson.io)
  - `gemeinde_substation.csv`: mapping of communities to substations


## Installation

### 1. Install Python

Required version: **Python 3.13**  
Download from: [https://www.python.org/downloads/](https://www.python.org/downloads/)

### 2. Install dependencies

Navigate to the project folder and create a virtual environment. Then install the dependencies using
```bash
pip install -r requirements.txt
```


## Usage

```bash
python main.py [options]
```

### Available options

| Option                           | Description                                                          |
| -------------------------------- | -------------------------------------------------------------------- |
| `-h`, `--help`                   | Show help message and exit                                           |
| `-v`, `--verbose`                | Print additional information                                         |
| `-n`, `--name`                   | Name of result directory                                             | 
| `-m`, `--model`                  | Path to model to use                                                 | 
| `-uc`, `--use_cache`             | Use cached data to avoid processing lines and substations            |
| `-gj`, `--geojson`               | Create a GeoJSON map of the grid                                     |
| `-ms`, `--missing_consumer_subs` | Create a CSV listing the ELWOG substations not found in the OSM data |


### Example commands

* Create a simulation model using cached data:

  ```bash
  python main.py
  ```

* Create model and GeoJSON, and show additional information:

  ```bash
  python main.py -gj -v
  ```


## How it Works

This project builds a representation of the Austrian power grid using several CSV files. These contain information on substations, power generators, and high-voltage power lines. Most data originates from OSM and is manually amended to address missing or incorrect entries.

Additional substations are synthesized to close open ends of lines (e.g. cross-border lines or line splits). These helper substations are excluded from final exports unless required as leafs for the graph.

### Connecting substations to communities and generators

* Each consumer is connected to a substation based on available public data

* Power generators are connected to the nearest substation, without any filtering based on voltage or region.

A shapefile of Austria’s states is used to assign each substation and community to the correct *Bundesland*.


### Connecting substations via power lines

* OSM provides information on high-voltage lines and the reference IDs of individual systems they carry.
* Multiple systems may share physical infrastructure, so connections are based on matching reference numbers (`ref` fields).
* In the model, each `Line` object connects exactly two substations (or helper substations).


## Related Projects

* **[Nurzu Load Flow Simulation](https://gitlab.sba-research.org/eris/nurzu-load-flow-simulation)**\
  Simulates power flow using the model produced by this project.

* **[Get OSM data](gitlab.sba-research.org/eris/get-osm-data)**\
  Collects power grid infrastructure data from OSM.

* **Deprecated:**\
  [Nurzu Load Flow Analysis](https://gitlab.sba-research.org/johanna/nurzu-load-flow-analysis) (this project and *Nurzu Load Flow Simulation* replace it)

