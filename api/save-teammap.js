const admin = require("firebase-admin");

if (!admin.apps.length) {
  const serviceAccount = JSON.parse(process.env.FIREBASE_SERVICE_ACCOUNT);

  admin.initializeApp({
    credential: admin.credential.cert(serviceAccount),
    databaseURL: "https://supersonic-l-default-rtdb.asia-southeast1.firebasedatabase.app/"
  });
}

module.exports = async function handler(req, res) {
  if (req.method !== "POST") {
    return res.status(405).json({ ok: false, error: "POST only" });
  }

  try {
    const { area, changes } = req.body;

    if (!area || !changes) {
      return res.status(400).json({ ok: false, error: "area/changes missing" });
    }

    const database = admin.database();

    const settingsRef = database.ref(`/settings/${area}/teamMap`);
    await settingsRef.update(changes);

    const liveRef = database.ref(`/live/${area}/riders`);
    const ridersSnap = await liveRef.get();

    if (ridersSnap.exists()) {
      const riderList = ridersSnap.val();
      const updates = {};

      Object.entries(riderList).forEach(([index, rider]) => {
        if (rider && rider.name && changes[rider.name]) {
          updates[`${index}/team`] = changes[rider.name];
        }
      });

      if (Object.keys(updates).length > 0) {
        await liveRef.update(updates);
      }
    }

    return res.status(200).json({ ok: true });
  } catch (e) {
    console.error(e);
    return res.status(500).json({ ok: false, error: e.message });
  }
};
