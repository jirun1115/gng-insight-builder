# Greenhouse gas emissions by sector - Data package

This data package contains the data that powers the chart ["Greenhouse gas emissions by sector"](https://ourworldindata.org/grapher/ghg-emissions-by-sector?v=1&csvType=full&useColumnShortNames=false) on the Our World in Data website.

### Active Filters

A filtered subset of the full data was downloaded. The following filters were applied:

## CSV structure

Each row is an observation for an entity (usually a country or region) at a timepoint.

- "Entity" — the name of the entity, e.g. "United States".
- "Code" — our internal entity code. For most countries this is the [ISO alpha-3](https://en.wikipedia.org/wiki/ISO_3166-1_alpha-3) code, e.g. "USA"; historical and other non-standard entities get a custom code.
- "Year" or "Day" — the timepoint. Annual data has a "Year" column holding an integer year; otherwise a "Day" column holds a date string in the form "YYYY-MM-DD".
- Every remaining column is a data column, each one a time series. Downloaded with the "full data" option each corresponds to one time series below; with "only selected data visible in the chart" they are transformed depending on the chart type, so the correspondence may be less direct.


## Metadata.json structure

The .metadata.json file contains metadata about the data package. The "charts" key contains information to recreate the chart, like the title, subtitle etc. The "columns" key contains information about each of the columns in the csv, like the unit, timespan covered, citation for the data etc.

## How we process data at Our World in Data

Our World in Data is almost never the original producer of the data - almost all of the data we use has been compiled by others. If you want to re-use data, it is your responsibility to ensure that you adhere to the sources' license and to credit them correctly. Please note that a single time series may have more than one source - e.g. when we stitch together data from different time periods by different producers or when we calculate per capita metrics using population data from a second source.

Preparing this data involves several processing steps. Depending on the data, this can include standardizing country names and world region definitions, converting units, calculating derived indicators such as per capita measures, as well as adding or adapting metadata such as the name or the description given to an indicator.
[Read about our data pipeline](https://docs.owid.io/projects/etl/).

## Detailed information about each time series


### Agriculture
Emissions are measured in tonnes of carbon dioxide-equivalents.
Last updated: February 10, 2026  
Next expected update: February 2027  
Date range: 1990–2023  
Unit: tonnes  
Source: Climate Watch (2026) – with major processing by Our World in Data  

#### How to cite this data

Climate Watch (2026) – with major processing by Our World in Data

#### How this data is described by its producers
Agriculture sector contains emissions from the following activities:
  - CH₄ emissions from Enteric fermentation (livestock).
  - CH₄ and N₂O emissions from Manure management (livestock).
  - CH₄ emissions from Rice cultivation.
  - N₂O emissions from Agriculture soils.
  - Crop residues.
  - Drained organic soils.
  - Manure applied to soils.
  - Manure left on pasture.
  - Synthetic fertilizers.
  - CH₄ and N₂O emissions from Other agricultural sources (burning of crop residues and savanna).

  Please note that emissions associated with agriculture related energy use are reported under Energy sector, and thus not included here.


### Land-use change and forestry
Emissions are measured in tonnes of carbon dioxide-equivalents.
Last updated: February 10, 2026  
Next expected update: February 2027  
Date range: 1990–2023  
Unit: tonnes  
Source: Climate Watch (2026) – with major processing by Our World in Data  

#### How to cite this data

Climate Watch (2026) – with major processing by Our World in Data

#### How this data is described by its producers
Land-Use Change and Forestry sector contains emissions from the following activities:
  - CO₂ emissions from Forest land and Net forest conversion (forestland converted to cropland and grassland).
  - CO₂ emissions from Drained organic soils.
  - CO₂ and CH₄ emissions from Fires in organic soils.
  - CH₄ and N₂O emissions from Forest fires.

  Please note that the forest land emissions data reflects emissions from changes in forest land area between reported years of Forest Resource Assessment (FRA) submitted by countries. The data is published every 5 years, and emissions values are estimated by interpolating data over those 5-year periods.

  Please note recent change of FAO's approach for reporting emissions from fires in organic soils (part of the "Burning Biomass"): only values from Southern-east Asia countries are included in country, regional and global aggregates (of burning biomass and subsequently land use total).


### Waste
Emissions are measured in tonnes of carbon dioxide-equivalents.
Last updated: February 10, 2026  
Next expected update: February 2027  
Date range: 1990–2023  
Unit: tonnes  
Source: Climate Watch (2026) – with major processing by Our World in Data  

#### How to cite this data

Climate Watch (2026) – with major processing by Our World in Data

#### How this data is described by its producers
Waste sector contains emissions from the following activities:
  - CH₄ from Landfills (including industrial and municipal solid waste).
  - CH₄ and N₂O from Wastewater treatment (rural and urban).
  - CH₄ and N₂O from Other waste sources.


### Buildings
Emissions are measured in tonnes of carbon dioxide-equivalents.
Last updated: February 10, 2026  
Next expected update: February 2027  
Date range: 1990–2023  
Unit: tonnes  
Source: Climate Watch (2026) – with major processing by Our World in Data  

#### How to cite this data

Climate Watch (2026) – with major processing by Our World in Data

#### How this data is described by its producers
Building subsector contains CO₂, CH₄ and N₂O emissions from the following activities:
  - Residential.
  - Commercial and public services.

  Please note that only on-site fuel combustion is covered here. Emissions associated with use of electricity are reported under electricity/heat.


### Industry
Emissions are measured in tonnes of carbon dioxide-equivalents.
Last updated: February 10, 2026  
Next expected update: February 2027  
Date range: 1990–2023  
Unit: tonnes  
Source: Climate Watch (2026) – with major processing by Our World in Data  

#### How to cite this data

Climate Watch (2026) – with major processing by Our World in Data

#### How this data is described by its producers
Industry sector contains emissions from the following activities:
  - CO₂ emissions from Cement Manufacture.
  - N₂O emissions from Adipic and Nitric Acid Production.
  - F-Gases from Electronics Manufacturing (semiconductor, flat panel display (FPD) and photovoltaic (PV)).
  - SF6 from Electric Power Systems.
  - PFCs and SF6 from Metal Production (PFCs as by-product of aluminum production, SF6 from magnesium production).
  - HFCs from Uses of Substitutes for Ozone-Depleting Substances (ODS).
  - HFCs from HCFC-22 Production.
  - N₂O and CH₄ emissions from Other Industrial activities (non-agriculture).

  Please note that for the purpose of Climate Watch dataset, all fluorinated gases are reported as aggregated F-gas.


### Manufacturing and construction
Emissions are measured in tonnes of carbon dioxide-equivalents.
Last updated: February 10, 2026  
Next expected update: February 2027  
Date range: 1990–2023  
Unit: tonnes  
Source: Climate Watch (2026) – with major processing by Our World in Data  

#### How to cite this data

Climate Watch (2026) – with major processing by Our World in Data

#### How this data is described by its producers
Manufacturing/Construction subsector contains CO₂, CH₄ and N₂O emissions from the following activities:
  - Mining and quarrying.
  - Construction.
  - Manufacturing.
  - Iron and Steel.
  - Chemical and petrochemical.
  - Non-ferrous metals.
  - Non-metallic minerals.
  - Transport equipment.
  - Machinery.
  - Food and tobacco.
  - Paper, pulp and printing.
  - Wood and wood products.
  - Textile and leather.
  - Non-specified industry.

  Please note that part of the emissions might be reallocated to industrial processes and product use category under the 2006 IPCC GLs.


### Transport
Emissions are measured in tonnes of carbon dioxide-equivalents.
Last updated: February 10, 2026  
Next expected update: February 2027  
Date range: 1990–2023  
Unit: tonnes  
Source: Climate Watch (2026) – with major processing by Our World in Data  

#### How to cite this data

Climate Watch (2026) – with major processing by Our World in Data

#### How this data is described by its producers
Transportation subsector contains CO₂, CH₄ and N₂O emissions from the following activities:
  - Road.
  - Rail.
  - Domestic aviation.
  - Pipeline transport.
  - Domestic navigation.
  - Non-specified transport (all emissions from transport not specified elsewhere).

  Please note that transport emissions for world total includes international marine bunkers and international aviation bunkers, which are not included in transportation at a national or regional level.


### Electricity and heat
Emissions are measured in tonnes of carbon dioxide-equivalents.
Last updated: February 10, 2026  
Next expected update: February 2027  
Date range: 1990–2023  
Unit: tonnes  
Source: Climate Watch (2026) – with major processing by Our World in Data  

#### How to cite this data

Climate Watch (2026) – with major processing by Our World in Data

#### How this data is described by its producers
Electricity/heat subsector contains CO₂, CH₄ and N₂O emissions from the following activities:
  - Main activity producer of electricity and heat (electricity plants, combined heat and power plants, heat plants).
  - Unallocated autoproducers.
  - Other energy industry own use.

  Please note that part of the emissions might be reallocated to industrial processes and product use category under the 2006 IPCC GLs.


### Fugitive emissions
Emissions are measured in tonnes of carbon dioxide-equivalents.
Last updated: February 10, 2026  
Next expected update: February 2027  
Date range: 1990–2023  
Unit: tonnes  
Source: Climate Watch (2026) – with major processing by Our World in Data  

#### How to cite this data

Climate Watch (2026) – with major processing by Our World in Data

#### How this data is described by its producers
Fugitive Emissions subsector contains fugitive CO₂ and CH₄ emissions from the following activities:
  - CO₂ from Flaring.
  - CH₄ from Coal mining.
  - CH₄ from Natural gas and oil systems.
  - Production.
  - Flaring and venting.
  - Transmission and distribution.
  - CH₄ and N₂O from Other energy sources (solid fuels, oil and natural gas, incineration and open burning of waste).


### Other fuel combustion
Emissions are measured in tonnes of carbon dioxide-equivalents.
Last updated: February 10, 2026  
Next expected update: February 2027  
Date range: 1990–2023  
Unit: tonnes  
Source: Climate Watch (2026) – with major processing by Our World in Data  

#### How to cite this data

Climate Watch (2026) – with major processing by Our World in Data

#### How this data is described by its producers
Other fuel combustion subsector contains emissions from the following activities:
  - CO₂, CH₄, and N₂O emissions from Agriculture/forestry, fishing, and other fuel consumption.

  Other fuel consumption includes emissions from military fuel use.


### Aviation and shipping
Emissions are measured in tonnes of carbon dioxide-equivalents.
Last updated: February 10, 2026  
Next expected update: February 2027  
Date range: 1990–2023  
Unit: tonnes  
Source: Climate Watch (2026) – with major processing by Our World in Data  

#### How to cite this data

Climate Watch (2026) – with major processing by Our World in Data

#### How this data is described by its producers
Bunker fuels contain CO₂ emissions from international marine and aviation bunkers. The split of domestic and international are determined by the departure and landing locations, and not by the nationality of the ship/airline.

  Bunker Fuels are shown as a sector, but excluded from national totals for Energy (including energy subsector Transport) and Total GHG emissions, in accordance with IPCC Guidelines. In other words, except at World level, Total GHG emissions (and accordingly Energy sector, and Transport sub-sector emissions) do not include bunker fuel emissions.


## Sources

These are the sources behind the data in this package. Each time series above names the ones it draws on in its citation.

### Climate Watch – Greenhouse gas emissions by sector

Climate Watch Historical Emissions data contains sector-level greenhouse gas (GHG) emissions, including emissions of the six major GHGs from most major sources and sinks. Non-CO₂ emissions are expressed in CO₂ equivalents using 100-year global warming potential values from the Intergovernmental Panel on Climate Change (IPCC) Fifth Assessment Report (AR5).

More information about their data sources and methodology can be found in their [FAQ page](https://www.climatewatchdata.org/about/faq/ghg). Specifically, the definitions of all Climate Watch data sectors and their methodology are explained in [this document](https://files.wri.org/d8/s3fs-public/2024-05/climate-watch-country-greenhouse-gas-emissions-data-methodology.pdf?VersionId=1geU96keSmqZlUjv41FNGB4CLpHQbruN).

Producer: Climate Watch  
Published: 2026-01-15  
Retrieved on: 2026-02-10  
Retrieved from: https://www.climatewatchdata.org/data-explorer/historical-emissions  
License: CC BY 4.0 (https://www.climatewatchdata.org/about/permissions)  

Citation: Climate Watch. 2026. Washington, DC: World Resources Institute (WRI). Available online at: https://www.climatewatchdata.org

Climate Watch data are derived from several sources.
- Data on land-Use change and forestry, and agriculture, are sourced from the Food and Agriculture Organization of the United Nations, FAOSTAT Emissions Database.
- Data on greenhouse gas emissions from fuel combustion are sourced from the OECD/IEA.

    