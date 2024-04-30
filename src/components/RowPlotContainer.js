
import React, { useState, useEffect} from "react";
import SingleTemplatePlot from "./SingleTemplatePlot";
import ProbePlot from "./ProbePlot";
import DataTablePlot from "./DataTablePlot";

import { openGroup } from "zarr";
import calculatePeakToPeakValues from "../utils/CalculationUtils";
import { percentageToFilterChannels } from "../styles/StyleConstants";


const RowPlotContainer = ({ templateIndex, storeRef, dataDictionary, isSelected, toggleSelection }) => {
  const [isLoading, setIsLoading] = useState(true);
  const [probeXCoordinates, setProbeXCoordinates] = useState([]);
  const [probeYCoordinates, setProbeYCoordinates] = useState([]);
  const [location, setLocation] = useState([0, 0]);
  const [samplingFrequency, setSamplingFrequency] = useState(null);
  const [activeIndices, setActiveIndices] = useState([]);
  const [templateArray, setTemplateArray] = useState([]);
  const [tableData, setTableData] = useState([]);

  useEffect(() => {
    const loadData = async () => {
      try {

        const zarrGroup = await openGroup(storeRef);
        const probeGroup = await openGroup(storeRef, "probe", "r");

        // Fetch sampling frequency
        const attributes = await zarrGroup.attrs.asObject();
        setSamplingFrequency(attributes["sampling_frequency"]);

        // Fetch probe data
        const xCoords = await probeGroup.getItem("x").then((data) => data.get(null));
        const yCoords = await probeGroup.getItem("y").then((data) => data.get(null));
        setProbeXCoordinates(xCoords.data);
        setProbeYCoordinates(yCoords.data);

        // Fetch template data for a specific index
        const templateArray = await zarrGroup.getItem("templates_array");
        setTemplateArray(templateArray);
        const singleTemplate = await templateArray.get([templateIndex, null, null]);
        
        const peakToPeakValues = calculatePeakToPeakValues(singleTemplate);
        const bestChannel = peakToPeakValues.indexOf(Math.max(...peakToPeakValues));

        // Active indices calculation
        const _activeIndices = peakToPeakValues
          .map((value, index) => (value >= peakToPeakValues[bestChannel] * percentageToFilterChannels ? index : null))
          .filter((index) => index !== null);
        setActiveIndices(_activeIndices);

        // Set location based on best channel
        const locationX = xCoords.data[bestChannel];
        const locationY = yCoords.data[bestChannel];
        setLocation([locationX, locationY]);

        // Set table data (mockup or real)
        const brainArea = dataDictionary["brain_area"][templateIndex];
        const NumberOfSpikes = dataDictionary["spikes_per_unit"][templateIndex]
        const bestChannelID = dataDictionary["channel_ids"][bestChannel]
        const UnitID = dataDictionary["unit_ids"][templateIndex]

        const peakToPeakBestChannel = peakToPeakValues[bestChannel]
        const peakToPeakBestChannelDecimalsRounded = peakToPeakBestChannel.toFixed(2)

        const data = [
          // { attribute: "Template Index", value: templateIndex},
          // { attribute: "Channel with max amplitude", value: bestChannel },
          { attribute: "UnitID", value: UnitID },
          { attribute: "Number of Spikes", value: NumberOfSpikes },
          { attribute: "Best ChannelID", value: bestChannelID},
          { attribute: "Brain Location", value: brainArea},
          { attribute: "Peak To Peak (uV)", value: peakToPeakBestChannelDecimalsRounded},
          { attribute: "Depth (um)", value: location[1]},

        ];
        setTableData(data);

        setIsLoading(false);
      } catch (error) {
        console.error("Error loading data for template index " + templateIndex + ":", error);
        setIsLoading(false);
      }
    };

    loadData();
  }, [templateIndex, storeRef]); // Dependency array to ensure re-fetching when these values change

  if (isLoading) {
    return <div>Loading data for template {templateIndex}...</div>;
  }

  return (
    <div className="RowPlotContainer">
      <div className="checkbox-container">
        <label>
          <input type="checkbox" checked={isSelected} onChange={() => toggleSelection(templateIndex)} /> Select
        </label>
      </div>
      <div className="template-plot">
        <SingleTemplatePlot
          templateIndex={templateIndex}
          templateArray={templateArray}
          probeXCoordinates={probeXCoordinates}
          probeYCoordinates={probeYCoordinates}
          activeIndices={activeIndices}
          samplingFrequency={samplingFrequency}
        />
      </div>
      <div className="probe-plot">
        <ProbePlot
          templateIndex={templateIndex}
          xCoordinates={probeXCoordinates}
          yCoordinates={probeYCoordinates}
          location={location}
          activeIndices={activeIndices}
        />
      </div>
      <div className="table-plot">
        <DataTablePlot tableData={tableData} />
      </div>
    </div>
  );
};

export default RowPlotContainer;
