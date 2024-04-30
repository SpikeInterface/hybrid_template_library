import React, { useState, useEffect} from "react";
import { HTTPStore } from "zarr";
import { FetchStore, open, get} from "zarrita";

import CodeSnippet from "./CodeSnippet";
import RowPlotContainer from "./RowPlotContainer";
import "../styles/App.css";
//const url = "http://localhost:8000/zarr_store.zarr";
const url = "https://spikeinterface-template-database.s3.us-east-2.amazonaws.com/test_templates";

const url = process.env.TEST_URL || "https://s3.amazonaws.com/my-bucket/templates";


function App() {
  const storeRef = new HTTPStore(url);
  
  const [selectedTemplates, setSelectedTemplates] = useState(new Set()); // Updated to useState
  const [templateIndices, setTemplateIndices] = useState([]);
  const [hasMore, setHasMore] = useState(true);
  const batchSize = 10;
  const [dataDictionary, setDataDictionary] = useState({});

  const loadTempalteIndices = () => {
    const nextIndex = templateIndices.length === 0 ? 0 : Math.max(...templateIndices) + 1;
    const newIndices = Array.from({ length: batchSize }, (_, i) => i + nextIndex);

    setTemplateIndices((prevIndices) => [...new Set([...prevIndices, ...newIndices])]);
    if (nextIndex + batchSize >= 100) {
      setHasMore(false);
    }
  };


  async function loadSessionData() {

    const store = new FetchStore(url);
    const root = await open(store, { kind: "group" });
  
    const brainAreaZarrArray = await open(root.resolve("brain_area"), { kind: "array" });
    const brainAreaArrayData = await get(brainAreaZarrArray, null);
    const brainAreaArrayJS = Array.from(brainAreaArrayData.data);
  
    const unitIdsZarrArray = await open(root.resolve("unit_ids"), { kind: "array" });
    const unitIdsArrayData = await get(unitIdsZarrArray, null);
    const unitIdsArrayJS = Array.from(unitIdsArrayData.data);
    const unitIDsArrayJSString = unitIdsArrayJS.map(String)


    const ChannelIDsZarrArray = await open(root.resolve("channel_ids"), { kind: "array" });
    const ChannelIDsArrayData = await get(ChannelIDsZarrArray, null);
    const ChannelIDsArrayJS = Array.from(ChannelIDsArrayData.data);
    const ChannelIDsArrayJSString = ChannelIDsArrayJS.map(String)

    const SpikesPerUnitZarrArray = await open(root.resolve("spikes_per_unit"), { kind: "array" });
    const SpikesPerUnitArrayData = await get(SpikesPerUnitZarrArray, null);
    const SpikesPerUnitArrayJS = Array.from(SpikesPerUnitArrayData.data);

    
    const BestChannelsZarrArray = await open(root.resolve("channel_ids"), { kind: "array" });
    const BestChannelsArrayData = await get(BestChannelsZarrArray, null);
    const BestChannelsArrayJS = Array.from(BestChannelsArrayData.data);

    let dataDictionary_ = {}; 
    dataDictionary_["brain_area"] = brainAreaArrayJS;
    dataDictionary_["unit_ids"] = unitIDsArrayJSString;
    dataDictionary_["spikes_per_unit"] = SpikesPerUnitArrayJS
    dataDictionary_["channel_ids"] = ChannelIDsArrayJSString
    dataDictionary_["best_channels"] = BestChannelsArrayJS


    setDataDictionary(dataDictionary_);
  }

  const toggleTemplateSelection = (templateIndex) => {
    const newSet = new Set(selectedTemplates);
    if (newSet.has(templateIndex)) {
      newSet.delete(templateIndex);
    } else {
      newSet.add(templateIndex);
    }
    setSelectedTemplates(newSet); // Trigger re-render
  };

  useEffect(() => {
    loadTempalteIndices();
    loadSessionData();
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
            dataDictionary={dataDictionary}
            storeRef={storeRef}
            isSelected={selectedTemplates.has(templateIndex)}
            toggleSelection={() => toggleTemplateSelection(templateIndex)}
          />
        ))}
      </div>
      {hasMore && (
        <button onClick={loadTempalteIndices} className="load-more-button">
          Load More Templates
        </button>
      )}
    </div>
  );
}

export default App;
