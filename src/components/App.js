import React, { useState, useEffect} from "react";
import { HTTPStore } from "zarr";

import CodeSnippet from "./CodeSnippet";
import RowPlotContainer from "./RowPlotContainer";
import "../styles/App.css";

function App() {
  const url = "https://spikeinterface-template-database.s3.us-east-2.amazonaws.com/test_templates";
  //const url = "http://localhost:8000/zarr_store.zarr";
  const storeRef = new HTTPStore(url);
  const [selectedTemplates, setSelectedTemplates] = useState(new Set()); // Updated to useState
  const [templateIndices, setTemplateIndices] = useState([]);
  const [hasMore, setHasMore] = useState(true);
  const batchSize = 15;

  const loadTemplates = () => {
    const nextIndex = templateIndices.length === 0 ? 0 : Math.max(...templateIndices) + 1;
    const newIndices = Array.from({ length: batchSize }, (_, i) => i + nextIndex);

    setTemplateIndices((prevIndices) => [...new Set([...prevIndices, ...newIndices])]);
    if (nextIndex + batchSize >= 100) {
      setHasMore(false);
    }
  };

  const toggleTemplateSelection = (templateIndex) => {
    const newSet = new Set(selectedTemplates);
    if (newSet.has(templateIndex)) {
      newSet.delete(templateIndex);
    } else {
      newSet.add(templateIndex);
    }
    setSelectedTemplates(newSet); // Trigger re-render
    console.log("Selected Templates: ", Array.from(newSet));
  };

  useEffect(() => {
    loadTemplates();
  }, []);

  return (
    <div className="App">
      <h2>Templates</h2>
      <CodeSnippet selectedTemplates={selectedTemplates} />

      <div className="ColumnPlotContainer">
        {templateIndices.map((templateIndex) => (
          <RowPlotContainer
            key={templateIndex}
            templateIndex={templateIndex}
            storeRef={storeRef}
            isSelected={selectedTemplates.has(templateIndex)}
            toggleSelection={() => toggleTemplateSelection(templateIndex)}
          />
        ))}
      </div>
      {hasMore && (
        <button onClick={loadTemplates} className="load-more-button">
          Load More Templates
        </button>
      )}
    </div>
  );
}

export default App;
