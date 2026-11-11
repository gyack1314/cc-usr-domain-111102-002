from workbench.domain import timestamp,observation
def check(c,root,read):
    rows=read(root/'samples/voyages.json')
    c.assertEqual(observation(rows[0])['exit'],4*86400)
    c.assertEqual(observation(rows[3])['kind'],'censor')
    c.assertFalse(observation(rows[4])['included'])
    c.assertEqual(timestamp('2026-01-01T08:00:00+08:00'),timestamp('2026-01-01T00:00:00Z'))
    with c.assertRaises(ValueError):observation(read(root/'samples/bad_records.json')[0])
