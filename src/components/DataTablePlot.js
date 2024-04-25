import React from "react";

function DataTablePlot({tableData}) {

  
  return (
    <div>
      <table>
        <thead>
          <tr>
            <th>Template property</th>
            <th>Value</th>
          </tr>
        </thead>
        <tbody>
          {tableData.map((row, index) => (
            <tr key={index}>
              <td>{row.attribute}</td>
              <td>{row.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default DataTablePlot;
