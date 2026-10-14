# Memory behaviour, and the 1.0.1 regression fixed in 1.0.2

**Summary.** 1.0.1 made `DarkSoulsIII.exe` appear to use ~4 GB more RAM than vanilla. The cause
was neither a leak nor the parameter writes: it was the table search reading every committed page
of the process. 1.0.2 finds the same tables without touching a single page the OS has paged out —
in game the memory footprint is now indistinguishable from vanilla (1624 MB vs 1634 MB peak
working set, where 1.0.1 peaked at 6007 MB).

## 1. Why reading memory costs physical RAM

| Term | Where you see it | Meaning |
|---|---|---|
| commit / private bytes | Task Manager → "Commit size" | memory the process has *reserved*; backed by the pagefile when it is not in RAM |
| resident / working set | Task Manager → "Memory" (default column) | pages that currently occupy physical RAM |
| paged out | not shown | the OS reclaimed the page: a dirty private page was written to `pagefile.sys`, a file-backed page was simply dropped |

Windows reclaims pages that have been written but not touched for a while. They stay committed —
the process still owns them — but they no longer occupy physical RAM. **Reading such a page faults
it back in**, and that costs physical memory again.

DS3 is the worst case for this, because it commits its resource pools (character models, textures,
animations, sound) during start-up. At the main menu the process holds

* ~8.07 GB of committed private memory, and
* ~1.6 GB of resident working set,

so roughly 6.4 GB of that pool sits in the pagefile and costs nothing. 1.0.1's scan read all of it,
once per second, until it found the tables — which turned that free memory back into real
occupancy. Reading `MEM_MAPPED` regions did the same to mapped files (the loose
`chr\*.chrbnd.dcx`, any memory-mapped archive).

It is not a leak: the commit charge is unchanged between vanilla and 1.0.1 (8055 MB vs 8035 MB in
the runs below). Only the resident share changed.

## 2. What 1.0.2 does instead

* `QueryWorkingSetEx` decides, per page, whether it is resident; `ScanForTables()` then copies only
  maximal runs of resident pages. A range the OS will not answer for is skipped entirely instead of
  being read "conservatively".
* No scan falls back to a full read. If the table is not resident yet, the engine has not loaded it
  yet, so the worker sleeps one second and retries (600 attempts = 10 minutes). The parameter
  tables are written by the engine when it loads the regulation data, so they are resident once
  they exist.
* `ScanMapped=1` stays available as a diagnostic, but it too reads only resident pages.
* Every scan logs its own cost:

```
scan: 4 table(s); read 1131 MB resident, left 29680 MB untouched of 30812 MB seen; working set 811 MB (peak 815 MB)
```

"read … resident" is memory the process was already holding; "left … untouched" is what the old
build would have faulted back in.

## 3. Measurements

### 3.1 Synthetic stand-in (`research\runtime\scan-test.cpp`)

A test host that commits 3 GB, touches only ~1/32 of it, maps a 974 MB file read-only without ever
touching it, then loads a mod DLL and reports the working set once a second:

| DLL loaded | before load | after load |
|---|---|---|
| 1.0.1 | 99 MB | **4010 MB** |
| 1.0.2 | 99 MB | **99 MB** (peak 103 MB) |

1.0.2's log line for that run: `read 100 MB resident, left 2976 MB untouched of 3076 MB seen`.
The 4 MB difference in the peak is the scan buffer itself.

### 3.2 In game (`research\runtime\ram-ab.ps1`)

`DarkSoulsIII.exe` launched the same way every time, working set sampled every 2 s for 100 s:

| build | t = 10 s | t = 30 s | peak working set | free system RAM at end |
|---|---|---|---|---|
| vanilla (`LoadCore=0`) | 158 MB | 1607 MB | 1634 MB | 13661 MB |
| 1.0.1 | **4351 MB** | 6000 MB | **6007 MB** | 9588 MB |
| 1.0.2 | 160 MB | 1591 MB | **1624 MB** | 13610 MB |

1.0.1 jumps from 171 MB to 4351 MB between two consecutive samples — that single step is the
reported "~4 GB".

### 3.3 On/off, interleaved (A/B/A/B)

Same installed files, nothing changed but `LoadCore` in the ini:

| run | `LoadCore` | steady-state working set (last 30 s) | peak | steady private | free RAM delta |
|---|---|---|---|---|---|
| A1 | 0 | 1609 MB | 1610 MB | 8055 MB | −1731 MB |
| B1 | 1 | 1618 MB | 1621 MB | 8062 MB | −1733 MB |
| A2 | 0 | 1612 MB | 1612 MB | 8062 MB | −1701 MB |
| B2 | 1 | 1608 MB | 1609 MB | 8061 MB | −1616 MB |
| — | **off** | **1610.5 MB** | — | 8058.5 MB | −1716 MB |
| — | **on** | **1613.0 MB** | — | 8061.5 MB | −1674.5 MB |

Difference: +2.5 MB working set, +3 MB private — smaller than the spread between two runs of the
*same* setting (3 MB off, 10 MB on). The only visible cost is a ~5 MB peak during start-up
(t = 8–12 s), which is the 4 MB scan buffer plus the table snapshot.

### 3.4 The effect still works

1.0.2's in-game log: `param tables located: 4` → `applied 2548 field write(s) over 364 row(s) in 4
table(s)` — identical to 1.0.1's output.

## 4. How to check your own install

1. Play for a minute (the main menu is enough), then open `HideSheathedLeft.log` next to the game
   executable.
2. The second line names the build: `--- HideSheathedLeft 1.0.2 loaded (pid …) ---`.
3. Look at the `scan:` line. `read` should be tens to a few hundred MB and `left … untouched`
   should be several GB. If `read` is several GB, the build is 1.0.1 or older.
4. Compare Task Manager's Memory column for `DarkSoulsIII.exe` with and without the mod
   (`LoadCore=0` disables this mod without uninstalling anything). Once the game has settled the
   two should be within a few MB of each other.

## 5. Regression risk

* If a table happens to be paged out at scan time, the mod no longer forces it in; it retries once
  a second instead. The effect can therefore appear slightly later after start-up, and it recovers
  by itself as soon as the engine touches the table again.
* `ScanMapped=1` remains available in case a table copy ever turns out to live in a mapped region.
* Nothing about the writes changed, so no game-side behaviour changes.
