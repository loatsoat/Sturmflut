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


_COORD_STATE_BG = {
    'IDLE':    '#d1fae5',
    'WAITING': '#fef3c7',
    'HELD':    '#fee2e2',
}
_COORD_STATE_BORDER = {
    'IDLE':    '2px solid #6ee7b7',
    'WAITING': '2px solid #fcd34d',
    'HELD':    '2px solid #f87171',
}


def _render_coord_panel(resource_state, coord_log):
    """Observer-only panel for the Leitstelle: shows charging-station state."""
    import time as _time

    rs    = resource_state or {}
    state = rs.get('state', 'IDLE')
    owner = rs.get('owner') or '—'
    ltime = rs.get('logical_time', 0)
    bg    = _COORD_STATE_BG.get(state,    '#f3f4f6')
    bord  = _COORD_STATE_BORDER.get(state,'2px solid #d1d5db')

    # Count how many distinct nodes are currently in each state from the log
    recent = (coord_log or [])[-30:]
    # last known state per node
    node_states = {}
    for entry in recent:
        nid = entry.get('node_id')
        if nid:
            node_states[nid] = entry.get('state', '?')
    waiting_nodes = [n for n, s in node_states.items() if s == 'WAITING']
    held_nodes    = [n for n, s in node_states.items() if s == 'HELD']

    # Flash animation only when something is active
    flash_style = ''
    if state in ('WAITING', 'HELD'):
        flash_style = (
            '<style>'
            '@keyframes coord-pulse {0%{opacity:1}50%{opacity:0.5}100%{opacity:1}}'
            '.coord-active{animation:coord-pulse 1s ease-in-out infinite}'
            '</style>'
        )

    active_class = 'coord-active' if state in ('WAITING', 'HELD') else ''

    # Last-updated wall time
    last_updated = rs.get('_wall_time', '')
    last_updated_str = f'  –  Letzte Änderung: <strong>{last_updated}</strong>' if last_updated else ''

    # Node status badges
    badge_html = ''
    for nid, nstate in sorted(node_states.items()):
        nbg   = _COORD_STATE_BG.get(nstate, '#f3f4f6')
        nbord = _COORD_STATE_BORDER.get(nstate, '1px solid #ccc')
        badge_html += (
            f'<span style="display:inline-block;margin:2px 4px;padding:2px 8px;'
            f'background:{nbg};border:{nbord};border-radius:10px;'
            f'font-family:monospace;font-size:11px">'
            f'{nid}: {nstate}</span>'
        )

    header = (
        f'{flash_style}'
        f'<div class="{active_class}" style="padding:8px 12px;background:{bg};border:{bord};'
        f'border-radius:4px;margin-bottom:4px;font-family:monospace">'
        f'<strong>Ladestation (Ricart/Agrawala)</strong> &nbsp;|&nbsp; '
        f'Zustand: <strong>{state}</strong> &nbsp;|&nbsp; '
        f'Inhaber: <strong>{owner}</strong> &nbsp;|&nbsp; '
        f'Logische Zeit: <strong>{ltime}</strong>'
        f'{last_updated_str} &nbsp;|&nbsp; '
        f'<em style="color:#6b7280">Leitstelle beobachtet nur (kein zentraler Eingriff)</em>'
        f'</div>'
    )

    # Node badges row
    badges_row = (
        f'<div style="margin-bottom:6px">{badge_html}</div>'
        if badge_html else ''
    )

    # Queue depth indicators
    queue_info = ''
    if waiting_nodes:
        queue_info = (
            f'<div style="font-family:monospace;font-size:11px;color:#92400e;'
            f'margin-bottom:4px">⏳ Wartend: {", ".join(waiting_nodes)}</div>'
        )
    if held_nodes:
        queue_info += (
            f'<div style="font-family:monospace;font-size:11px;color:#991b1b;'
            f'margin-bottom:4px">🔒 Hält Ladestation: {", ".join(held_nodes)}</div>'
        )

    log_lines = []
    for entry in recent[-15:]:
        e_state = entry.get('state', '?')
        e_node  = entry.get('node_id', '?')
        e_owner = entry.get('owner') or '—'
        e_lt    = entry.get('logical_time', 0)
        e_wall  = entry.get('_wall_time', '')
        e_bg    = _COORD_STATE_BG.get(e_state, '#f3f4f6')
        e_bord  = _COORD_STATE_BORDER.get(e_state, '1px solid #ccc')
        wall_str = f' [{e_wall}]' if e_wall else ''
        log_lines.append(
            f'<span style="background:{e_bg};border:{e_bord};padding:1px 5px;border-radius:3px">'
            f'{e_node}</span> → <strong>{e_state}</strong>'
            f'  owner={e_owner}  t={e_lt}{wall_str}'
        )

    log_html  = '<br>'.join(log_lines) if log_lines else 'Noch keine Koordinationsnachrichten'
    log_block = (
        f'<div id="coord-log" style="font-family:monospace;font-size:12px;padding:8px;'
        f'background:#f9fafb;border:1px solid #e5e7eb;border-radius:4px;'
        f'white-space:pre-wrap;line-height:1.8">{log_html}</div>'
    )

    # Fast-poll: fetch /status every 1s and update only the coord section via JS
    fast_poll_js = (
        '<script>'
        '(function(){'
        '  function updateCoord(){'
        '    fetch("/status").then(r=>r.json()).then(function(d){'
        '      var rs=d.resource_state||{};'
        '      var log=d.coord_log||[];'
        '      var states={IDLE:"#d1fae5",WAITING:"#fef3c7",HELD:"#fee2e2"};'
        '      var borders={IDLE:"2px solid #6ee7b7",WAITING:"2px solid #fcd34d",HELD:"2px solid #f87171"};'
        '      var hdr=document.getElementById("coord-hdr");'
        '      if(hdr){'
        '        var s=rs.state||"IDLE";'
        '        hdr.style.background=states[s]||"#f3f4f6";'
        '        hdr.style.border=borders[s]||"2px solid #d1d5db";'
        '        hdr.innerHTML="<strong>Ladestation</strong> | Zustand: <strong>"+s'
        '          +"</strong> | Inhaber: <strong>"+(rs.owner||"—")'
        '          +"</strong> | Zeit: <strong>"+rs.logical_time+"</strong>";'
        '      }'
        '      var logDiv=document.getElementById("coord-log");'
        '      if(logDiv&&log.length){'
        '        var bg={IDLE:"#d1fae5",WAITING:"#fef3c7",HELD:"#fee2e2"};'
        '        var lines=log.slice(-15).map(function(e){'
        '          var c=bg[e.state]||"#f3f4f6";'
        '          return "<span style=\'background:"+c+";padding:1px 5px;border-radius:3px\'>"'
        '            +e.node_id+"</span> → <strong>"+e.state+"</strong>"'
        '            +"  owner="+(e.owner||"—")+"  t="+e.logical_time;'
        '        });'
        '        logDiv.innerHTML=lines.join("<br>");'
        '      }'
        '    }).catch(function(){});'
        '  }'
        '  setInterval(updateCoord, 1000);'
        '  updateCoord();'
        '})();'
        '</script>'
    )

    return (
        f'<div style="margin-top:10px;font-family:Arial,sans-serif">'
        f'<strong>Koordinations-Log (letzte 15 Einträge)</strong>'
        f'<div id="coord-hdr" style="padding:8px 12px;background:{bg};border:{bord};'
        f'border-radius:4px;margin:4px 0">'
        f'<strong>Ladestation</strong> | Zustand: <strong>{state}</strong> | '
        f'Inhaber: <strong>{owner}</strong> | Zeit: <strong>{ltime}</strong>'
        f'</div>'
        f'{badges_row}'
        f'{queue_info}'
        f'{log_block}'
        f'{fast_poll_js}'
        f'</div>'
    )


def render(map_data, units, incidents, active_missions, mission_log, history,
           resource_state=None, coord_log=None):
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
        _render_coord_panel(resource_state, coord_log),
        '<script>setTimeout(()=>location.reload(),3000)</script>',
        '</div>',
    ]
    return '\n'.join(rows)
