import React from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
// Choose a style that mimics a terminal
import { vs } from 'react-syntax-highlighter/dist/esm/styles/prism';

function CodeSnippet({ selectedTemplates }) {
  const generatePythonCode = (selectedTemplates) => {
    const selectedUnitIndicesString = JSON.stringify([...selectedTemplates], null, 2);
    return `from spikeinterface.hybrid import generate_recording_from_template_database
selected_unit_indices = ${selectedUnitIndicesString}
durations = [1.0]  # Specify the duration for each template
recording = generate_recording_from_template_database(selected_unit_indices, durations=durations)`;
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