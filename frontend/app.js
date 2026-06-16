

console.log("Dashboard script loaded");

async function updateDashboard() {
  const response = await fetch("/latest");

  const data = await response.json();

  document.getElementById("counter").textContent = data.counter.value;
}

setInterval(updateDashboard, 1000);
