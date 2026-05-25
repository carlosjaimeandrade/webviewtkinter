window.receive.ping_python((params) => {
  document.getElementById("result").innerText =
    "Callback from Python:\n" + JSON.stringify(params, null, 2);
});

async function callPython() {
  await window.send.ping_python("index.html", "home", 1);
}

async function openTopLevel() {
  await window.send.top_level("index.html", "open-top-level");
}
