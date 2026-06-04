const database = admin.database();

await database
  .ref(`/settings/${area}/teamMap`)
  .set(teamMap);

const liveRef = database.ref(`/live/${area}/riders`);
const riders = await liveRef.get();

if (riders.exists()) {
  const riderList = riders.val();

  const updates = {};
 Object.entries(riderList).forEach(([index, rider]) => {
  if (rider && rider.name && teamMap[rider.name]) {
    updates[`${index}/team`] = teamMap[rider.name];
  }
});

  if (Object.keys(updates).length > 0) {
    await liveRef.update(updates);
  }
}

return res.status(200).json({ ok: true });
