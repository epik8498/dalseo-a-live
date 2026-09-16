const admin = require("firebase-admin");

const DATABASE_URL =
  "https://supersonic-l-default-rtdb.asia-southeast1.firebasedatabase.app/";

function getFirebaseApp() {
  if (admin.apps.length) return admin.app();

  const raw = process.env.FIREBASE_SERVICE_ACCOUNT;
  if (!raw) {
    throw new Error("FIREBASE_SERVICE_ACCOUNT environment variable is missing");
  }

  let serviceAccount;
  try {
    serviceAccount = JSON.parse(raw);
  } catch (e) {
    throw new Error("FIREBASE_SERVICE_ACCOUNT is not valid JSON");
  }

  if (serviceAccount.private_key) {
    serviceAccount.private_key = String(serviceAccount.private_key).replace(/\\n/g, "\n");
  }

  return admin.initializeApp({
    credential: admin.credential.cert(serviceAccount),
    databaseURL: DATABASE_URL
  });
}

function normalizePhone(value) {
  return String(value || "").replace(/\D/g, "");
}

function firebaseSafeKey(value) {
  return String(value || "")
    .trim()
    .replace(/[.#$\[\]\/]/g, "_");
}

function stableKeys(rider) {
  const keys = [];
  const phone = normalizePhone(rider && rider.phone);
  const userId = firebaseSafeKey(rider && rider.userId);

  if (phone) keys.push("phone_" + phone);
  if (userId) keys.push("uid_" + userId);

  return [...new Set(keys)];
}

function normalizeChanges(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    throw new Error("changes must be an object");
  }

  const clean = {};
  for (const [keyRaw, teamRaw] of Object.entries(raw)) {
    const key = String(keyRaw || "").trim();
    const team = String(teamRaw || "").trim();

    if (!(key.startsWith("phone_") || key.startsWith("uid_"))) continue;
    if (!team || team.length > 60) continue;

    clean[key] = team;
  }

  if (!Object.keys(clean).length) {
    throw new Error("no valid rider changes");
  }

  if (Object.keys(clean).length > 1000) {
    throw new Error("too many rider changes");
  }

  return clean;
}

function validateArea(areaRaw) {
  const area = String(areaRaw || "").trim();
  if (!/^[a-z0-9_-]{1,50}$/i.test(area)) {
    throw new Error("invalid area");
  }
  return area;
}

function teamForRider(rider, changes) {
  for (const key of stableKeys(rider)) {
    if (Object.prototype.hasOwnProperty.call(changes, key)) {
      return changes[key];
    }
  }
  return "";
}

async function updateRiderList(database, path, changes, aliasUpdates) {
  const ref = database.ref(path);
  const snap = await ref.get();
  if (!snap.exists()) return 0;

  const riders = snap.val() || {};
  const updates = {};
  let count = 0;

  Object.entries(riders).forEach(([index, rider]) => {
    if (!rider || typeof rider !== "object") return;

    const newTeam = teamForRider(rider, changes);
    if (!newTeam) return;

    updates[`${index}/team`] = newTeam;
    count += 1;

    stableKeys(rider).forEach((key) => {
      aliasUpdates[key] = newTeam;
    });
  });

  if (Object.keys(updates).length) {
    await ref.update(updates);
  }

  return count;
}

module.exports = async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") {
    return res.status(204).end();
  }

  if (req.method !== "POST") {
    return res.status(405).json({ ok: false, error: "POST only" });
  }

  try {
    getFirebaseApp();

    const body = req.body || {};
    const area = validateArea(body.area);
    const changes = normalizeChanges(body.changes);

    const database = admin.database();
    const aliasUpdates = { ...changes };

    const liveUpdated = await updateRiderList(
      database,
      `/live/${area}/riders`,
      changes,
      aliasUpdates
    );

    const liveLiteUpdated = await updateRiderList(
      database,
      `/live-lite/${area}/riders`,
      changes,
      aliasUpdates
    );

    await database.ref(`/settings/${area}/teamMap`).update(aliasUpdates);

    return res.status(200).json({
      ok: true,
      area,
      requested: Object.keys(changes).length,
      storedKeys: Object.keys(aliasUpdates).length,
      liveUpdated,
      liveLiteUpdated
    });
  } catch (e) {
    console.error("save-teammap error:", e);
    return res.status(500).json({
      ok: false,
      error: e && e.message ? e.message : String(e)
    });
  }
};
