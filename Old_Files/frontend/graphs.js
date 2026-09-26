console.log("graphs.js loaded");
console.log("Plotly is:", Plotly);

const lastGraphTimestamps = {};

function buildTestGraph() {
  Plotly.newPlot(
    "counterGraph",
    [
      {
        x: [1, 2, 3, 4],
        y: [10, 20, 15, 30],
        mode: "lines",
        name: "Counter",
      },
    ],
    {
      title: "Counter vs Time",
    },
  );
}

async function buildTimeGraph(sensor) {
  const response = await fetch(`/history/${sensor}`);
  const data = await response.json();
  const x = data.map((packet) => packet.timestamp);
  const y = data.map((packet) => packet.value);
  const units = data.length > 0 ? data[0].unit : "";

  Plotly.newPlot(
    `${sensor}Graph`,
    [
      {
        //time on x axis, values on y axis
        x: x,
        y: y,
        mode: "lines",
        name: sensor,
      },
    ],
    {
      title: `${sensor} vs Time`,
      xaxis: {
        title: "Time (ms)",
      },
      yaxis: {
        title: `${sensor} (${units})`,
      },
    },
  );
  if (data.length > 0) {
    lastGraphTimestamps[sensor] = data[data.length - 1].timestamp;
  }
}

async function updateTimeGraph(sensor) {
  //find the latest values for each sensor recorded
  const response = await fetch("/latest");
  const data = await response.json();

  //if there are no logs of the sensor type we want in latest data, return
  if (!data[sensor]) {
    return;
  }

  const packet = data[sensor];
  //if timestamp is same as lastGraphTimestamp[sensor], return
  if (packet.timestamp == lastGraphTimestamps[sensor]) {
    return;
  }

  lastGraphTimestamps[sensor] = packet.timestamp;

  //update graph
  Plotly.extendTraces(
    `${sensor}Graph`,
    {
      x: [[packet.timestamp]],
      y: [[packet.value]],
    },
    [0],
    100,
  );
}

async function startGraph(sensor) {
  await buildTimeGraph(sensor);

  setInterval(() => {
    updateTimeGraph(sensor);
  }, 1000);
}

startGraph("counter");
