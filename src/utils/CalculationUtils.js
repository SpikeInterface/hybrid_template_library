function calculatePeakToPeakValues(single_template) {
  const numberOfChannels = single_template.shape[1];
  const peak_to_peak_values = new Array(numberOfChannels).fill(0).map((_, channelIndex) => {
    let channelMax = -Infinity;
    let channelMin = Infinity;
    single_template.data.forEach((sample) => {
      const value = sample[channelIndex];
      if (value > channelMax) channelMax = value;
      if (value < channelMin) channelMin = value;
    });
    return channelMax - channelMin;
  });
  return peak_to_peak_values;
}

export default calculatePeakToPeakValues;
