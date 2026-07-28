import express from "express";
import path from "path";
import fs from "fs";
import { createServer as createViteServer } from "vite";
import multer from "multer";
import AdmZip from "adm-zip";

import { CONFIG } from "./src/server/config.js";
import { ensureDirectories, logger, generateTempFilename } from "./src/server/utils.js";

// Prevent server crash on uncaught exception or unhandled promise rejection
process.on("uncaughtException", (error) => {
  logger.error("Uncaught Exception caught:", error);
});

process.on("unhandledRejection", (reason, promise) => {
  logger.error("Unhandled Rejection caught at promise:", promise, "reason:", reason);
});
import {
  initDb,
  getOrCreateUser,
  addCoins,
  removeCoins,
  addSubscription,
  removeSubscription,
  getQueue,
  clearQueue,
  addToQueue,
  getHistory,
  getAllUsers,
  getGroupChatId,
  setGroupChatId,
} from "./src/server/database.js";
import { startTelegramBot, handleIncomingCommand, announceTransactionToGroup } from "./src/server/bot.js";

// Setup storage and database on boot
ensureDirectories();

const app = express();
app.use(express.json());

// Set up Multer for handling file uploads from the Web UI Simulator
const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    cb(null, "./temp");
  },
  filename: (req, file, cb) => {
    const userId = req.body.userId || "web_user";
    const tempName = generateTempFilename(userId, file.originalname);
    cb(null, path.basename(tempName));
  },
});
const upload = multer({ storage });

// API ROUTES (Always register API routes FIRST!)

// Endpoint to download the entire project source code as a ZIP file
app.get("/api/download-zip", (req, res) => {
  try {
    const zip = new AdmZip();
    const rootDir = process.cwd();
    const excludeList = ["node_modules", "dist", "temp", ".git", ".env"];

    const items = fs.readdirSync(rootDir);
    for (const item of items) {
      if (excludeList.includes(item)) continue;
      const fullPath = path.join(rootDir, item);
      const stat = fs.statSync(fullPath);
      if (stat.isDirectory()) {
        zip.addLocalFolder(fullPath, item);
      } else if (stat.isFile()) {
        zip.addLocalFile(fullPath);
      }
    }

    const zipBuffer = zip.toBuffer();
    res.setHeader("Content-Type", "application/zip");
    res.setHeader("Content-Disposition", 'attachment; filename="pokemon-go-bot-source.zip"');
    res.send(zipBuffer);
  } catch (err: any) {
    logger.error("Failed to generate zip file:", err);
    res.status(500).json({ error: "Failed to generate project zip: " + err.message });
  }
});

// Endpoint to download bot.py directly
app.get("/bot.py", (req, res) => {
  const botPyPath = path.join(process.cwd(), "bot.py");
  if (fs.existsSync(botPyPath)) {
    res.setHeader("Content-Type", "text/x-python; charset=utf-8");
    res.setHeader("Content-Disposition", 'attachment; filename="bot.py"');
    res.sendFile(botPyPath);
  } else {
    res.status(404).send("bot.py not found");
  }
});

// Endpoint to view or download requirements.txt directly
app.get("/requirements.txt", (req, res) => {
  const reqPath = path.join(process.cwd(), "requirements.txt");
  if (fs.existsSync(reqPath)) {
    res.setHeader("Content-Type", "text/plain; charset=utf-8");
    res.setHeader("Content-Disposition", 'attachment; filename="requirements.txt"');
    res.sendFile(reqPath);
  } else {
    res.status(404).send("requirements.txt not found");
  }
});

// Endpoint to download render.yaml directly
app.get("/render.yaml", (req, res) => {
  const yamlPath = path.join(process.cwd(), "render.yaml");
  if (fs.existsSync(yamlPath)) {
    res.setHeader("Content-Type", "text/yaml; charset=utf-8");
    res.setHeader("Content-Disposition", 'attachment; filename="render.yaml"');
    res.sendFile(yamlPath);
  } else {
    res.status(404).send("render.yaml not found");
  }
});

// Endpoint to download package.json directly
app.get("/package.json", (req, res) => {
  const pkgPath = path.join(process.cwd(), "package.json");
  if (fs.existsSync(pkgPath)) {
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.setHeader("Content-Disposition", 'attachment; filename="package.json"');
    res.sendFile(pkgPath);
  } else {
    res.status(404).send("package.json not found");
  }
});

// Endpoint to download src/package.json directly
app.get("/src/package.json", (req, res) => {
  const srcPkgPath = path.join(process.cwd(), "src", "package.json");
  if (fs.existsSync(srcPkgPath)) {
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.setHeader("Content-Disposition", 'attachment; filename="package.json"');
    res.sendFile(srcPkgPath);
  } else {
    res.status(404).send("src/package.json not found");
  }
});

// Endpoint to download yarn.lock directly
app.get("/yarn.lock", (req, res) => {
  const yarnPath = path.join(process.cwd(), "yarn.lock");
  if (fs.existsSync(yarnPath)) {
    res.setHeader("Content-Type", "text/plain; charset=utf-8");
    res.setHeader("Content-Disposition", 'attachment; filename="yarn.lock"');
    res.sendFile(yarnPath);
  } else {
    res.status(404).send("yarn.lock not found");
  }
});

// Endpoint to download src/yarn.lock directly
app.get("/src/yarn.lock", (req, res) => {
  const srcYarnPath = path.join(process.cwd(), "src", "yarn.lock");
  if (fs.existsSync(srcYarnPath)) {
    res.setHeader("Content-Type", "text/plain; charset=utf-8");
    res.setHeader("Content-Disposition", 'attachment; filename="yarn.lock"');
    res.sendFile(srcYarnPath);
  } else {
    res.status(404).send("src/yarn.lock not found");
  }
});

// Endpoint to generate and download full project ZIP
app.get(["/project.zip", "/api/download-zip"], (req, res) => {
  try {
    const zip = new AdmZip();
    zip.addLocalFolder(process.cwd(), "", (filename) => {
      const normalized = filename.replace(/\\/g, "/");
      if (
        normalized.includes("node_modules/") ||
        normalized.includes("dist/") ||
        normalized.includes(".git/") ||
        normalized.includes(".vite/") ||
        normalized.endsWith(".zip")
      ) {
        return false;
      }
      return true;
    });
    const buffer = zip.toBuffer();
    res.setHeader("Content-Type", "application/zip");
    res.setHeader("Content-Disposition", 'attachment; filename="telegram-ai-ocr-bot.zip"');
    res.send(buffer);
  } catch (err) {
    console.error("Failed to generate zip:", err);
    res.status(500).send("Error generating zip file");
  }
});

app.get("/api/requirements", (req, res) => {
  const reqPath = path.join(process.cwd(), "requirements.txt");
  if (fs.existsSync(reqPath)) {
    const content = fs.readFileSync(reqPath, "utf-8");
    res.json({ content });
  } else {
    res.status(404).json({ error: "requirements.txt not found" });
  }
});

// 1. Get status of the system (is Telegram Bot running, are secrets set, database info)
app.get("/api/status", async (req, res) => {
  try {
    const hasBotToken = !!CONFIG.BOT_TOKEN;
    const hasGroqKey = !!CONFIG.GROQ_API_KEY;
    const hasGeminiKey = !!CONFIG.GEMINI_API_KEY;
    const users = await getAllUsers();
    
    res.json({
      botOnline: hasBotToken,
      secrets: {
        hasBotToken,
        hasGroqKey,
        hasGeminiKey,
      },
      stats: {
        totalUsers: users.length,
        adminUserId: CONFIG.ADMIN_ID,
        groupChatId: getGroupChatId(),
      },
    });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// 2. Simulator: Send text message to simulated bot
app.post("/api/simulator/message", async (req, res) => {
  const { userId, username, text } = req.body;
  if (!userId || !text) {
    res.status(400).json({ error: "Missing userId or text" });
    return;
  }

  const responses: string[] = [];
  const replyCollector = async (msg: string) => {
    responses.push(msg);
  };

  try {
    await handleIncomingCommand(userId, username || "Web Trainer", text, replyCollector);
    res.json({ responses });
  } catch (error: any) {
    logger.error("Simulator message error:", error);
    res.status(500).json({ error: error.message || "Internal simulator error" });
  }
});

// 3. Simulator: Upload a screenshot to the temporary queue
app.post("/api/simulator/upload", upload.single("screenshot"), async (req, res) => {
  const { userId } = req.body;
  if (!userId || !req.file) {
    res.status(400).json({ error: "Missing userId or screenshot file" });
    return;
  }

  try {
    const filePath = req.file.path;
    await addToQueue(userId, filePath);
    
    const queue = await getQueue(userId);
    res.json({
      success: true,
      queueLength: queue.length,
      message: `✅ Screenshot received successfully!\n\n• Total screenshots in queue: *${queue.length}*\n• Upload more screenshots if needed.\n\nWhen finished, send: /generate`,
    });
  } catch (error: any) {
    logger.error("Simulator upload error:", error);
    res.status(500).json({ error: error.message || "Internal upload error" });
  }
});

// 4. Admin API: Get all registered users
app.get("/api/admin/users", async (req, res) => {
  try {
    const users = await getAllUsers();
    res.json({ users });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// 5. Admin API: Get specific user details & history
app.get("/api/admin/user/:userId", async (req, res) => {
  const { userId } = req.params;
  try {
    const user = await getOrCreateUser(userId);
    const history = await getHistory(userId);
    const queue = await getQueue(userId);
    res.json({ user, history, queueLength: queue.length });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// 6. Admin API: Modify coins
app.post("/api/admin/coins", async (req, res) => {
  const { userId, amount, action } = req.body; // action: 'add' | 'remove'
  if (!userId || isNaN(amount)) {
    res.status(400).json({ error: "Invalid user or amount" });
    return;
  }

  try {
    if (action === "add") {
      await addCoins(userId, amount);
    } else {
      await removeCoins(userId, amount);
    }
    const updatedUser = await getOrCreateUser(userId);

    // Announce to Telegram Group
    const userDisplay = updatedUser.username && updatedUser.username !== "Trainer" 
      ? `@${updatedUser.username}` 
      : `Trainer (ID: ${userId})`;
    if (action === "add") {
      await announceTransactionToGroup(
        `🔔 *TRANSACTION COMPLETED* 🔔\n\n` +
        `💰 Added *${amount}* Coins to user *${userDisplay}*.\n` +
        `✨ New Coins Balance: *${updatedUser.coins}* Coins.`
      );
    } else {
      await announceTransactionToGroup(
        `🔔 *TRANSACTION COMPLETED* 🔔\n\n` +
        `💸 Removed *${amount}* Coins from user *${userDisplay}*.\n` +
        `✨ New Coins Balance: *${updatedUser.coins}* Coins.`
      );
    }

    res.json({ success: true, user: updatedUser });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// 7. Admin API: Modify subscription
app.post("/api/admin/subscription", async (req, res) => {
  const { userId, plan } = req.body; // plan: '1d' | '3d' | '7d' | '31d' | '365d'
  if (!userId || !plan) {
    res.status(400).json({ error: "Missing userId or plan" });
    return;
  }

  try {
    const expiry = await addSubscription(userId, plan);
    const updatedUser = await getOrCreateUser(userId);

    // Announce to Telegram Group
    const userDisplay = updatedUser.username && updatedUser.username !== "Trainer" 
      ? `@${updatedUser.username}` 
      : `Trainer (ID: ${userId})`;
    await announceTransactionToGroup(
      `🔔 *SUBSCRIPTION ACTIVATED* 🔔\n\n` +
      `🎉 Plan *${plan.toUpperCase()}* has been granted to user *${userDisplay}*.\n` +
      `📅 Valid Until: *${new Date(expiry).toLocaleString()}*.`
    );

    res.json({ success: true, user: updatedUser, expiry });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// 8. Admin API: Expire subscription
app.post("/api/admin/subscription/expire", async (req, res) => {
  const { userId } = req.body;
  if (!userId) {
    res.status(400).json({ error: "Missing userId" });
    return;
  }

  try {
    await removeSubscription(userId);
    const updatedUser = await getOrCreateUser(userId);

    // Announce to Telegram Group
    const userDisplay = updatedUser.username && updatedUser.username !== "Trainer" 
      ? `@${updatedUser.username}` 
      : `Trainer (ID: ${userId})`;
    await announceTransactionToGroup(
      `🔔 *SUBSCRIPTION REVOKED* 🔔\n\n` +
      `⚠️ Subscription has been revoked for user *${userDisplay}*.`
    );

    res.json({ success: true, user: updatedUser });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// 8.5. Admin API: Set Telegram Group Chat ID
app.post("/api/admin/settings/group", async (req, res) => {
  const { groupChatId } = req.body;
  try {
    setGroupChatId(groupChatId || null);
    res.json({ success: true, groupChatId: getGroupChatId() });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// 9. Admin API: Clear user's screenshot queue
app.post("/api/admin/queue/clear", async (req, res) => {
  const { userId } = req.body;
  if (!userId) {
    res.status(400).json({ error: "Missing userId" });
    return;
  }

  try {
    await clearQueue(userId);
    res.json({ success: true });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});


// Bootstrapping function
async function startServer() {
  // Initialize Database
  await initDb();

  // Start Telegram Bot in parallel
  startTelegramBot();

  // Integrate Vite for Frontend UI
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  const PORT = CONFIG.PORT;
  app.listen(PORT, "0.0.0.0", () => {
    logger.info(`Fullstack Pokémon GO Bot Server running on http://localhost:${PORT}`);
  });
}

startServer();
