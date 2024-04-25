import { bestChannelColor, activeChannelsColor, plotFont} from "../styles/StyleConstants";
import calculatePeakToPeakValues from "../utils/CalculationUtils";
import React, { useEffect } from "react";
import Plot from "plotly.js-dist";

function SingleTemplatePlot({ templateIndex, templateArray, samplingFrequency, activeIndices }) {
  useEffect(() => {
    const loadPlotData = async () => {
      if (!templateArray) return; // Exit early if templateArray is not available

      try {
        const singleTemplate = await templateArray.get([templateIndex, null, null]);
        const peak_to_peak_values = calculatePeakToPeakValues(singleTemplate);
        const bestChannel = peak_to_peak_values.indexOf(Math.max(...peak_to_peak_values));
        const singleTemplateBestChannel = await singleTemplate.get([null, bestChannel]);

        const numberOfSamples = singleTemplate.shape[0];
        const xData = Array.from({ length: numberOfSamples }, (_, i) => i);
        const timeMilliseconds = xData.map((value) => (value / samplingFrequency) * 1000.0);

        // Initialize an array to hold plot data for all channels
        let plotData = [];

        plotData.push({
          x: timeMilliseconds,
          y: singleTemplateBestChannel.data,
          type: "scatter",
          mode: "lines",
          line: {
            color: bestChannelColor,
            width: 5,
            opacity: 1,
          },
          name: "Best Channel",
          showlegend: true,
        });

        const firstActiveChannelIndex = activeIndices[0];
        activeIndices.forEach((channelIndex) => {
          plotData.push({
            x: timeMilliseconds,
            y: singleTemplate.get([null, channelIndex]).data,
            type: "scatter",
            mode: "lines",
            line: {
              color: activeChannelsColor,
              width: 0.5,
              opacity: 0.1,
            },
            name: `Active Channels`,
            legendgroup: "Active Channels",
            showlegend: firstActiveChannelIndex === channelIndex,
            visible: "legendonly",
          });
        });

        const plotLayout = {
          title: `Template Index: ${templateIndex}`,
          autosize: true,
          font: plotFont,
          xaxis: { title: "Time (ms)", showgrid: false },
          yaxis: { title: "Amplitude (uV)", showgrid: false },
          legend: {
            x: 0.075,
            y: 0.075,
            xanchor: "left",
            yanchor: "bottom",
            bgcolor: 'rgba(0,0,0,0)', // Make legend background transparent
          },
        };
        const plotDivId = `plotDiv${templateIndex}`; // Unique ID for each plot
        Plot.newPlot(plotDivId, plotData, plotLayout, { displayModeBar: false, responsive: true});
      } catch (error) {
        console.error("Error loading plot data:", error);
      }
    };

    loadPlotData();
  }, [templateIndex, templateArray, samplingFrequency, activeIndices]); // Updated dependency array

  return <div id={`plotDiv${templateIndex}`}></div>;
}

export default SingleTemplatePlot;