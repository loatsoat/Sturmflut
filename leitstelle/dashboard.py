TERRAIN_BG   = {'sand': '#d9c77a', 'sand_light': '#f1e4a6', 'water': '#16719B'}
INFRA_COLOR  = {k: '#c94c4c' for k in ('helipad','depot','harbor','bridge','charging_station')}
INFRA_LABEL  = {'helipad':'HEL','depot':'DEP','harbor':'HAR','bridge':'BRG','charging_station':'CHG'}
UNIT_LABEL   = {'drone':'DRN','repair_rover':'RPR','supply_rover':'SUP','camera':'CAM','water_sensor':'WTR'}
UNIT_STYLE   = {
    'drone':        {'bg':'#c084fc','text':'#111','border':'1px solid #5e5e5e'},
    'repair_rover': {'bg':'#ef4444','text':'#fff','border':'1px solid #5e5e5e'},
    'supply_rover': {'bg':'#f59e0b','text':'#111','border':'1px solid #5e5e5e'},
    'camera':       {'bg':'#60a5fa','text':'#000','border':'2px solid #000'},
    'water_sensor': {'bg':'#2dd4bf','text':'#000','border':'1px solid #0f766e'},
    'supply_sensor':{'bg':'#86efac','text':'#000','border':'1px solid #14532d'},
}
_DEFAULT_STYLE = {'bg':'#c084fc','text':'#111','border':'1px solid #5e5e5e'}
_SZ = '30px'
_TD = ('width:{s};min-width:{s};max-width:{s};height:{s};min-height:{s};max-height:{s};'
       'padding:0;box-sizing:border-box;font-size:12px;line-height:1;font-weight:bold;'
       'text-align:center;vertical-align:middle;overflow:hidden;white-space:nowrap;'
       'background:{bg};color:{text};border:{border}')


def _td(bg, text, border, title, display):
    style = _TD.format(s=_SZ, bg=bg, text=text, border=border)
    return f'<td title="{title}" style="{style}">{display}</td>'


def render(map_data, units, incidents, active_missions, mission_log, history):
    w, h   = map_data['width'], map_data['height']
    cells  = {(c['x'], c['y']): c for c in map_data['cells']}
    placed = {(u.get('x'), u.get('y')): (uid, u)
              for uid, u in units.items()
              if isinstance(u.get('x'), int) and isinstance(u.get('y'), int)}

    rows = [
        '<div style="margin:8px auto;font-family:Arial,sans-serif;max-width:fit-content">',
        '<div style="margin-bottom:8px;font-size:14px">Live map – MQTT data. Refreshes every 3 s.</div>',
        '<table style="border-collapse:collapse">',
    ]

    for y in range(h):
        cols = ['<tr>']
        for x in range(w):
            c      = cells.get((x, y), {'type': 'water'})
            infra  = c.get('infrastructure', '')
            if infra:
                bg, text, border = INFRA_COLOR.get(infra,'#ffb703'), '#111', '1px solid #5e5e5e'
                display, title   = INFRA_LABEL.get(infra, infra[:3].upper()), infra.replace('_',' ')
            else:
                terrain = c.get('type', 'water')
                bg      = TERRAIN_BG.get(terrain, '#d9c77a')
                text    = '#fff' if terrain == 'water' else '#111'
                display, title, border = '', terrain, '1px solid #5e5e5e'

            if (x, y) in placed:
                uid, ud  = placed[(x, y)]
                role     = ud.get('role','unit')
                st       = UNIT_STYLE.get(role, _DEFAULT_STYLE)
                bg, text, border = st['bg'], st['text'], st['border']
                display  = UNIT_LABEL.get(role, uid[:3].upper())
                title    = f"{title} – {uid} ({role}, {ud.get('state','?')})"

            cols.append(_td(bg, text, border, title, display))
        cols.append('</tr>')
        rows.append(''.join(cols))

    rows.append('</table>')

    def pre(label, lines, width='260px'):
        body = '\n'.join(lines) if lines else f'No {label.lower()}'
        return (f'<div><strong>{label}</strong>'
                f'<pre style="margin:4px 0 0;padding:8px;background:#f6f6f6;'
                f'border:1px solid #ddd;min-width:{width};white-space:pre-wrap">{body}</pre></div>')

    ulines = [f"{uid}: {u.get('role')} {u.get('state')} @ ({u.get('x','?')},{u.get('y','?')})"
              for uid, u in list(units.items())[:12]]
    hlines = [f"#{i['id']} {i['type']} {i.get('value','')}" for i in history[-10:]]
    mlines = [f"{e['mission_id']} {e.get('unit_id','-')} {e['state']} {e.get('message','')}"
              for e in mission_log[-12:]]

    rows += [
        f'<p style="font-family:Arial,sans-serif">Units: {len(units)} | '
        f'Queued: {len(incidents)} | Active missions: {len(active_missions)}</p>',
        '<div style="display:flex;gap:24px;flex-wrap:wrap;margin-top:10px;font-family:Arial,sans-serif">',
        pre('Units', ulines),
        pre('Incident history', hlines),
        pre('Mission progress', mlines, '360px'),
        '</div>',
        '<script>setTimeout(()=>location.reload(),3000)</script>',
        '</div>',
    ]
    return '\n'.join(rows)
