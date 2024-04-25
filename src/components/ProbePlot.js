import { bestChannelColor, activeChannelsColor, plotFont } from "../styles/StyleConstants"; // Adjusted to match the file name case
import React, { useEffect } from "react";
import Plot from "plotly.js-dist";

function ProbePlot({ templateIndex, xCoordinates, yCoordinates, location, activeIndices }) {
  const y_location = location[1];
  let activeLocationsX = [];
  let activeLocationsY = [];
  for (const channelIndex of activeIndices) {
    activeLocationsX.push(xCoordinates[channelIndex]);
    activeLocationsY.push(yCoordinates[channelIndex]);
  }

  const minActiveLocationY = Math.min(...activeLocationsY);
  const maxActiveLocationY = Math.max(...activeLocationsY);

  const minY = Math.min(...yCoordinates);
  const maxY = Math.max(...yCoordinates);

  useEffect(() => {
    const plotData = [];
    const plotLayout = {
      title: {
        text: 'Location<br>In<br>Probe',
        font: plotFont,
        xref: 'paper',
        x: 0.5, // This centers the title
        y: 0.9 // You can adjust this to move the title up or down
      },      autosize: true,
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "#f0f0f0", // A solid color for the plot background if needed
      font: plotFont,
      xaxis: {
        showgrid: false,
        zeroline: false,
        showticklabels: false,
        showline: false,
        range: [0, 1],
      },
      yaxis: {
        title: "Depth (um)",
        showgrid: false,
        zeroline: false,
        range: [minY, maxY],
      },
      shapes: [
        // Adding a rectangle from minActiveLocationY to maxActiveLocationY
        {
          type: "rect",
          xref: "paper",
          yref: "y",
          x0: 0,
          y0: minActiveLocationY,
          x1: 1,
          y1: maxActiveLocationY,
          fillcolor: activeChannelsColor,
          line: {
            width: 0,
          },
        },
        // Adding a line for y_location
        {
          type: "line",
          xref: "paper",
          x0: 0,
          y0: y_location,
          x1: 1,
          y1: y_location,
          line: {
            color: bestChannelColor,
            width: 1,
          },
        },
      ],
    };

    const probePlotDivId = `probePlotDiv${templateIndex}`; // Unique ID for each plot
    Plot.newPlot(probePlotDivId, plotData, plotLayout, {
      displayModeBar: false,
      responsive: true,
    });
  }, [templateIndex]);

  return <div id={`probePlotDiv${templateIndex}`} ></div>;
}

export default ProbePlot;
