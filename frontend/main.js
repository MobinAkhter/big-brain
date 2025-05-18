const { app, BrowserWindow } = require("electron");
const path = require("path");
const { spawn } = require("child_process");

let backendProcess;

function createWindow() {
  const win = new BrowserWindow({
    width: 1000,
    height: 700,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
    },
  });
  win.loadFile("index.html");
  win.webContents.openDevTools(); // Automatically open DevTools for debugging
}

app.whenReady().then(() => {
  const pythonPath = "/Users/mobinakhter/Pycharm/second-brain/.venv/bin/python";
  const backendScript = path.join(__dirname, "integration.py");
  backendProcess = spawn(pythonPath, [backendScript], { stdio: "inherit" });
  setTimeout(createWindow, 2000); // Delay to ensure backend starts first
});

app.on("window-all-closed", () => {
  if (backendProcess) {
    backendProcess.kill();
  }
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});
