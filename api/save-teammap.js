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
    const { area, teamMap } = req.body;

    if (!area || !teamMap) {
      return res.status(400).json({ ok: false, error: "area/teamMap missing" });
    }

    await admin.database()
      .ref(`/settings/${area}/teamMap`)
      .set(teamMap);

    return res.status(200).json({ ok: true });
  } catch (e) {
    return res.status(500).json({ ok: false, error: e.message });
  }
};
