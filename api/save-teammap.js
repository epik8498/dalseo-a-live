const admin = require("firebase-admin");

if (!admin.apps.length) {
  const serviceAccount = JSON.parse(
    process.env.FIREBASE_SERVICE_ACCOUNT
  );

  admin.initializeApp({
    credential: admin.credential.cert(serviceAccount),
    databaseURL:
      "https://supersonic-l-default-rtdb.asia-southeast1.firebasedatabase.app/"
  });
}

function normalizePhone(value) {
  return String(value || "").replace(/\D/g, "");
}

module.exports = async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") {
    return res.status(204).end();
  }

  if (req.method !== "POST") {
    return res.status(405).json({
      ok: false,
      error: "POST only"
    });
  }

  try {
    const { area, changes } = req.body || {};

    if (
      !area ||
      !changes ||
      typeof changes !== "object" ||
      Array.isArray(changes)
    ) {
      return res.status(400).json({
        ok: false,
        error: "area/changes missing"
      });
    }

    const database = admin.database();

    const nameRef = database.ref(
      `/settings/${area}/teamMap`
    );

    const phoneRef = database.ref(
      `/settings/${area}/teamMapPhone`
    );

    const liveRef = database.ref(
      `/live/${area}/riders`
    );

    const ridersSnap = await liveRef.get();

    const phoneUpdates = {};
    const liveUpdates = {};

    if (ridersSnap.exists()) {
      const riderList = ridersSnap.val() || {};

      Object.entries(riderList).forEach(([index, rider]) => {
        if (!rider || !rider.name) return;

        const newTeam = changes[rider.name];
        if (!newTeam) return;

        // 현재 화면 데이터 즉시 변경
        liveUpdates[`${index}/team`] = newTeam;

        // 전화번호 기준 팀맵 변경
        const phone = normalizePhone(rider.phone);

        if (phone) {
          phoneUpdates[phone] = newTeam;
        }
      });
    }

    // 이름 기준 팀맵
    await nameRef.update(changes);

    // 전화번호 기준 팀맵
    if (Object.keys(phoneUpdates).length > 0) {
      await phoneRef.update(phoneUpdates);
    }

    // 실시간 기사 데이터
    if (Object.keys(liveUpdates).length > 0) {
      await liveRef.update(liveUpdates);
    }

    return res.status(200).json({
      ok: true,
      area,
      namesUpdated: Object.keys(changes).length,
      phonesUpdated: Object.keys(phoneUpdates).length,
      liveUpdated: Object.keys(liveUpdates).length
    });

  } catch (e) {
    console.error("save-teammap error:", e);

    return res.status(500).json({
      ok: false,
      error: e.message
    });
  }
};
