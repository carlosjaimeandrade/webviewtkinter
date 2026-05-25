window.receive.ping_python((params) => {
  document.getElementById("result").innerText =
    "Callback from Python:\n" + JSON.stringify(params, null, 2);
});

async function callPython() {
  const result = await window.send.ping_python("tela2.html", "screen2", { active: true });
  document.getElementById("result").innerText =
    "Direct return:\n" + result;
}
