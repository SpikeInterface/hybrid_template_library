import React from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
// Choose a style that mimics a terminal
import { vs } from 'react-syntax-highlighter/dist/esm/styles/prism';

function CodeSnippet({ selectedTemplates }) {
  const generatePythonCode = (selectedTemplates) => {
    const selectedUnitIndicesString = JSON.stringify([...selectedTemplates], null, 2);
    return `from spikeinterface.generation import fetch_templates_database_info, query_templates_from_database, generate_hybrid_recording
selected_unit_indices = ${selectedUnitIndicesString}

templates_info = fetch_templates_database_info()
templates = query_templates_from_database(templates_info.loc[selected_unit_indices])

# recording is an existing spikeinterface.BaseRecording
recording_hybrid = get_templates_from_database(recording, templates=templates)`;
  };

  const pythonCode = generatePythonCode(selectedTemplates);

  return (
    <div id="code-container">
      <SyntaxHighlighter language="python" style={vs} showLineNumbers={true}>
        {pythonCode}
      </SyntaxHighlighter>
    </div>
  );
}

export default CodeSnippet;