using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using SoulsFormats;

// Helper around DSAS's own SoulsFormats build (the library DS Anim Studio uses to
// read/write TAE and BND4), so patched bundles are produced and validated by the
// exact same code path the editor uses.
//
//   validate  <file>...              parse bundle + every TAE, report HideWeapon events
//   dump710   <file>                 list every HideEquippedWeapon (710) event
//   add       <in> <out> <spec.tsv>  insert HideEquippedWeapon events
//   roundtrip <in> <out>             read + rewrite unchanged (container sanity check)
//
// spec.tsv:  taeName <TAB> animId <TAB> paramsHex <TAB> start <TAB> end
//            taeName matches the basename of the bundle entry, e.g. "a00.tae"
internal static class Program
{
    private static int Main(string[] args)
    {
        if (args.Length < 2) { Usage(); return 2; }
        try
        {
            switch (args[0])
            {
                case "validate": return Validate(args.Skip(1).ToArray());
                case "scanid": return ScanId(args[1], args[2], args.Length > 3 ? args[3] : null);
                case "dumpids": return DumpIds(args[1], args[2], args.Length > 3 ? args[3] : null);
                case "flverdiff": return FlverDiff(args[1], args[2]);
                case "stripdir": return StripDir(args[1], args[2], args[3],
                                                args.Length > 4 ? args[4] : "chrbnd",
                                                args.Length > 5 && args[5] == "DRYRUN");
                case "parkdir": return ParkDir(args[1], args[2], args[3],
                                               args.Length > 4 ? args[4] : "0,-1000,0",
                                               args.Length > 5 ? args[5] : "0",
                                               args.Length > 6 ? args[6] : "chrbnd",
                                               args.Length > 7 && args[7] == "DRYRUN");
                case "park": return ParkDummy(args[1], args[2],
                                              args.Length > 3 ? args[3] : null,
                                              args.Length > 4 ? args[4] : "0,-300,0",
                                              args.Length > 5 ? args[5] : "0",
                                              args.Length > 6 ? args[6] : null);
                case "dummies": return Dummies(args[1]);
                case "inspect": return Inspect(args[1]);
                case "dump710": return Dump710(args[1]);
                case "add": return Add(args[1], args[2], args[3]);
                case "roundtrip": return RoundTrip(args[1], args[2]);
                default: Usage(); return 2;
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine("ERROR: " + ex);
            return 1;
        }
    }

    private static void Usage()
    {
        Console.WriteLine("usage: validate <file>... | dump710 <file> | add <in> <out> <spec.tsv> | roundtrip <in> <out>");
    }

    private static bool s_quiet;

    private static BND4 ReadBundle(string path, out byte[] payload, out DCX.Type dcxType)
    {
        byte[] raw = File.ReadAllBytes(path);
        if (DCX.Is(raw))
        {
            payload = DCX.Decompress(raw, out dcxType);
            if (!s_quiet)
                Console.WriteLine($"  {Path.GetFileName(path)}: DCX type={dcxType} payload={payload.Length} (file {raw.Length})");
        }
        else
        {
            payload = raw;
            dcxType = DCX.Type.None;
            if (!s_quiet)
                Console.WriteLine($"  {Path.GetFileName(path)}: raw (no DCX) {payload.Length} bytes");
        }
        return BND4.Read(payload);
    }

    /// <summary>Print "file<TAB>id,id,..." for every FLVER found under a root (for set analysis).</summary>
    private static int DumpIds(string root, string outPath, string nameFilter)
    {
        s_quiet = true;
        using var w = new StreamWriter(outPath, false, System.Text.Encoding.UTF8);
        int files = 0;
        foreach (string f in Directory.EnumerateFiles(root, "*", SearchOption.AllDirectories).OrderBy(x => x))
        {
            string low = f.ToLowerInvariant();
            if (!(low.EndsWith(".dcx") || low.EndsWith(".flver") || low.EndsWith(".bnd"))) continue;
            if (nameFilter != null && !low.Contains(nameFilter.ToLowerInvariant())) continue;
            try
            {
                FLVER2 flver = FirstFlver(f);
                if (flver == null) continue;
                files++;
                w.WriteLine(Path.GetFileName(f) + "\t" + string.Join(",", flver.Dummies.Select(d => (int)d.ReferenceID).Distinct().OrderBy(x => x)));
            }
            catch { }
        }
        w.Close();
        Console.WriteLine($"wrote {outPath}: {files} file(s)");
        return 0;
    }

    /// <summary>
    /// Walk a directory tree and report every bundle whose FLVER contains one of the
    /// given dummy ReferenceIDs -- used to prove a newly appended parking dummy cannot
    /// collide with a dummy id some other part of the character model already uses.
    /// </summary>
    private static int ScanId(string root, string idArg, string nameFilter)
    {
        var wanted = new HashSet<short>(idArg.Split(',').Select(s => short.Parse(s.Trim(), CultureInfo.InvariantCulture)));
        s_quiet = true;
        int files = 0, withFlver = 0, hits = 0, failed = 0;
        int overallMax = int.MinValue;
        string maxWhere = "";
        foreach (string f in Directory.EnumerateFiles(root, "*", SearchOption.AllDirectories)
                                       .OrderBy(x => x))
        {
            string low = f.ToLowerInvariant();
            if (!(low.EndsWith(".dcx") || low.EndsWith(".flver") || low.EndsWith(".bnd"))) continue;
            if (nameFilter != null && !low.Contains(nameFilter.ToLowerInvariant())) continue;
            files++;
            try
            {
                BND4 bnd;
                FLVER2 flver = null;
                if (low.EndsWith(".flver"))
                {
                    flver = FLVER2.Read(File.ReadAllBytes(f));
                }
                else
                {
                    bnd = ReadBundle(f, out _, out _);
                    foreach (BinderFile bf in bnd.Files)
                    {
                        if (!EntryName(bf).EndsWith(".flver", StringComparison.OrdinalIgnoreCase)) continue;
                        flver = FLVER2.Read(bf.Bytes);
                        break;
                    }
                }
                if (flver == null) continue;
                withFlver++;
                int mx = flver.Dummies.Count == 0 ? -1 : flver.Dummies.Max(d => (int)d.ReferenceID);
                if (mx > overallMax) { overallMax = mx; maxWhere = Path.GetFileName(f); }
                var got = flver.Dummies.Where(d => wanted.Contains(d.ReferenceID)).Select(d => d.ReferenceID).Distinct().ToList();
                if (got.Count > 0)
                {
                    hits++;
                    Console.WriteLine($"  HIT {Path.GetFileName(f)}: ids {string.Join(",", got)} (dummies={flver.Dummies.Count}, max={mx})");
                }
            }
            catch { failed++; }
        }
        Console.WriteLine($"scanned {files} file(s), {withFlver} with an FLVER, unreadable={failed}");
        Console.WriteLine($"files containing {string.Join("/", wanted)}: {hits}");
        Console.WriteLine($"highest dummy ReferenceID seen anywhere: {overallMax} (in {maxWhere})");
        return hits > 0 ? 1 : 0;
    }

    /// <summary>
    /// Structural comparison of the first FLVER in two bundles: bones, materials, meshes
    /// and buffer layouts must be identical; the dummy table is diffed entry by entry.
    /// </summary>
    private static int FlverDiff(string aPath, string bPath)
    {
        s_quiet = true;
        FLVER2 a = FirstFlver(aPath);
        FLVER2 b = FirstFlver(bPath);
        if (a == null || b == null) { Console.WriteLine("ERROR: no FLVER found in one of the files"); return 1; }

        Console.WriteLine($"bones   : {a.Bones.Count} vs {b.Bones.Count}  digest {Digest(Bones(a))} vs {Digest(Bones(b))}  {(Digest(Bones(a)) == Digest(Bones(b)) ? "SAME" : "DIFFERENT")}");
        Console.WriteLine($"materials: {a.Materials.Count} vs {b.Materials.Count}  digest {Digest(Materials(a))} vs {Digest(Materials(b))}  {(Digest(Materials(a)) == Digest(Materials(b)) ? "SAME" : "DIFFERENT")}");
        Console.WriteLine($"meshes  : {a.Meshes.Count} vs {b.Meshes.Count}  digest {Digest(Meshes(a))} vs {Digest(Meshes(b))}  {(Digest(Meshes(a)) == Digest(Meshes(b)) ? "SAME" : "DIFFERENT")}");
        Console.WriteLine($"layouts : {a.BufferLayouts.Count} vs {b.BufferLayouts.Count}  digest {Digest(Layouts(a))} vs {Digest(Layouts(b))}  {(Digest(Layouts(a)) == Digest(Layouts(b)) ? "SAME" : "DIFFERENT")}");

        var da = a.Dummies.Select((d, i) => (i, d.ReferenceID, d.ParentBoneIndex, d.AttachBoneIndex, d.Position)).ToList();
        var db = b.Dummies.Select((d, i) => (i, d.ReferenceID, d.ParentBoneIndex, d.AttachBoneIndex, d.Position)).ToList();
        Console.WriteLine($"dummies : {da.Count} vs {db.Count}");

        // compare by list index (vanilla entries must be untouched, appends at the end)
        int n = Math.Min(da.Count, db.Count);
        int moved = 0;
        for (int i = 0; i < n; i++)
        {
            var x = da[i]; var y = db[i];
            bool same = x.ReferenceID == y.ReferenceID && x.ParentBoneIndex == y.ParentBoneIndex &&
                        x.AttachBoneIndex == y.AttachBoneIndex &&
                        x.Position.X == y.Position.X && x.Position.Y == y.Position.Y && x.Position.Z == y.Position.Z;
            if (!same)
            {
                moved++;
                Console.WriteLine($"  changed dummy at index {i}: id {x.ReferenceID} bone {x.ParentBoneIndex} pos ({x.Position.X},{x.Position.Y},{x.Position.Z})  ->  id {y.ReferenceID} bone {y.ParentBoneIndex} pos ({y.Position.X},{y.Position.Y},{y.Position.Z})");
            }
        }
        for (int i = n; i < db.Count; i++)
            Console.WriteLine($"  appended dummy at index {i}: id {db[i].ReferenceID} bone {db[i].ParentBoneIndex} pos ({db[i].Position.X},{db[i].Position.Y},{db[i].Position.Z})");
        if (b.Dummies.Count < a.Dummies.Count)
            Console.WriteLine($"  WARNING: {a.Dummies.Count - b.Dummies.Count} dummy/entries removed");
        Console.WriteLine($"dummy entries changed: {moved} (0 = every vanilla entry preserved byte-for-byte)");
        return moved == 0 ? 0 : 1;
    }

    private static FLVER2 FirstFlver(string path)
    {
        string low = path.ToLowerInvariant();
        if (low.EndsWith(".flver")) return FLVER2.Read(File.ReadAllBytes(path));
        BND4 bnd = ReadBundle(path, out _, out _);
        foreach (BinderFile bf in bnd.Files)
        {
            if (!EntryName(bf).EndsWith(".flver", StringComparison.OrdinalIgnoreCase)) continue;
            return FLVER2.Read(bf.Bytes);
        }
        return null;
    }

    private static string Bones(FLVER2 f) =>
        string.Join("\n", f.Bones.Select(b => $"{b.Name}|{b.Translation}|{b.Rotation}|{b.Scale}|{b.BoundingBoxMin}|{b.BoundingBoxMax}|{b.ParentIndex}|{b.ChildIndex}|{b.NextSiblingIndex}|{b.PreviousSiblingIndex}|{b.Unk3C}"));

    private static string Materials(FLVER2 f) =>
        string.Join("\n", f.Materials.Select(m => $"{m.Name}|{m.MTD}|{m.Flags}|{m.Textures.Count}|{m.GXIndex}|{m.Unk18}"));

    private static string Meshes(FLVER2 f) =>
        string.Join("\n", f.Meshes.Select(m => $"{m.MaterialIndex}|{m.Vertices.Count}|{m.FaceSets.Count}|{m.BoneIndices.Count}"));

    private static string Layouts(FLVER2 f) =>
        string.Join("\n", f.BufferLayouts.Select(l => string.Join(",", l.Select(m => $"{m.Semantic}:{m.Type}:{m.Index}"))));

    private static string Digest(string s) =>
        Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(s))).Substring(0, 16);

    private static byte[] WriteBundle(BND4 bnd, byte[] originalFile, DCX.Type dcxType)
    {
        byte[] payload = bnd.Write();
        if (dcxType == DCX.Type.None && !DCX.Is(originalFile)) return payload;
        return DCX.Compress(payload, dcxType);
    }

    private static List<(string name, BinderFile file, TAE3 tae)> TaeEntries(BND4 bnd, out List<(string, Exception)> errors)
    {
        var list = new List<(string, BinderFile, TAE3)>();
        errors = new List<(string, Exception)>();
        foreach (BinderFile f in bnd.Files)
        {
            string name = Path.GetFileName((f.Name ?? "").Replace('\\', '/'));
            if (!name.EndsWith(".tae", StringComparison.OrdinalIgnoreCase)) continue;
            try { list.Add((name, f, TAE3.Read(f.Bytes))); }
            catch (Exception ex) { errors.Add((name, ex)); }
        }
        return list;
    }

    private static string Hex(TAE3.Event ev)
    {
        if (ev is TAE3.Event.HideWeapon hw)
            return $"{hw.Unk00:x2} {hw.Unk01:x2} {hw.Unk02:x2} {hw.Unk03:x2}";
        return ev.ToString();
    }

    /// <summary>List the dummy nodes of every FLVER in a bundle (attach points live here).</summary>
    /// <summary>
    /// Append one dummy attach point to every FLVER in a bundle, parked far away from the
    /// character, so a param attach field can point at it instead of at an invalid poly
    /// (an invalid poly makes the engine build a degenerate matrix: black triangles and
    /// full-screen flicker).
    /// </summary>
    private static int ParkDummy(string inPath, string outPath, string refIdArg, string posArg, string parentArg, string moveArg)
    {
        BND4 bnd = ReadBundle(inPath, out _, out DCX.Type dcxType);
        byte[] original = File.ReadAllBytes(inPath);
        float[] pos = posArg.Split(',').Select(s => float.Parse(s, CultureInfo.InvariantCulture)).ToArray();
        int parentBone = int.Parse(parentArg, CultureInfo.InvariantCulture);

        var before = new Dictionary<string, string>();
        foreach (BinderFile f in bnd.Files)
            before[EntryName(f)] = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(f.Bytes));

        bool done = false;
        foreach (BinderFile f in bnd.Files)
        {
            string name = EntryName(f);
            if (!name.EndsWith(".flver", StringComparison.OrdinalIgnoreCase)) continue;
            FLVER2 flver = FLVER2.Read(f.Bytes);

            int index = flver.Dummies.Count;
            short refId = refIdArg != null ? short.Parse(refIdArg, CultureInfo.InvariantCulture) : (short)index;
            int clashes = flver.Dummies.Count(d => d.ReferenceID == refId);

            // prototype only provides the orientation/flag values; the parent bone is the
            // character root by default so the offset is straight down in model space
            FLVER.Dummy proto = flver.Dummies.FirstOrDefault(d => d.AttachBoneIndex < 0)
                                ?? flver.Dummies[0];

            var nd = new System.Numerics.Vector3(pos[0], pos[1], pos[2]);
            var dummy = new FLVER.Dummy
            {
                ReferenceID = refId,
                ParentBoneIndex = (short)parentBone,
                AttachBoneIndex = -1,
                Position = nd,
                Forward = proto.Forward,
                Upward = proto.Upward,
                Color = proto.Color,
                Flag1 = proto.Flag1,
                UseUpwardVector = proto.UseUpwardVector,
                Unk30 = proto.Unk30,
                Unk34 = proto.Unk34,
            };
            flver.Dummies.Add(dummy);
            Console.WriteLine($"  {name}: appended dummy id={refId} at list index {index} " +
                              $"pos=({pos[0]},{pos[1]},{pos[2]}) parentBone={parentBone} " +
                              $"(existing dummies with this id: {clashes}) -> total {flver.Dummies.Count}");

            // optional: also move an EXISTING dummy (an id the engine already knows) to the
            // same parking spot, so HidePoly can be switched between the two candidates
            // without touching the model again
            if (moveArg != null)
            {
                var moveId = short.Parse(moveArg, CultureInfo.InvariantCulture);
                var existing = flver.Dummies.Where(d => d.ReferenceID == moveId).ToList();
                if (existing.Count == 0)
                    Console.WriteLine($"  WARNING: no existing dummy with id {moveId} to move");
                foreach (FLVER.Dummy d in existing)
                {
                    System.Numerics.Vector3 was = d.Position;
                    d.Position = nd;
                    d.ParentBoneIndex = (short)parentBone;
                    Console.WriteLine($"  moved existing dummy {moveId} from ({was.X},{was.Y},{was.Z}) to ({pos[0]},{pos[1]},{pos[2]}) ({existing.Count} entry/entries)");
                }
            }
            f.Bytes = flver.Write();
            done = true;
        }
        if (!done) { Console.WriteLine("ERROR: no .flver entry in " + inPath); return 1; }

        byte[] outBytes = WriteBundle(bnd, original, dcxType);
        File.WriteAllBytes(outPath, outBytes);
        Console.WriteLine($"wrote {outPath}: {outBytes.Length} bytes (original {original.Length})");

        BND4 back = ReadBundle(outPath, out _, out _);
        foreach (BinderFile f in back.Files)
        {
            string name = EntryName(f);
            string h = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(f.Bytes));
            if (before.TryGetValue(name, out string old) && old != h)
                Console.WriteLine($"  changed entry: {name} ({f.Bytes.Length} bytes)");
        }
        foreach (BinderFile f in back.Files)
        {
            string name = EntryName(f);
            if (!name.EndsWith(".flver", StringComparison.OrdinalIgnoreCase)) continue;
            FLVER2 v = FLVER2.Read(f.Bytes);
            FLVER.Dummy last = v.Dummies[v.Dummies.Count - 1];
            Console.WriteLine($"  verify {name}: dummies={v.Dummies.Count} last=(id {last.ReferenceID}, " +
                              $"pos {last.Position.X},{last.Position.Y},{last.Position.Z}, parentBone {last.ParentBoneIndex})");
        }
        return 0;
    }

    private static string EntryName(BinderFile f) =>
        Path.GetFileName((f.Name ?? "").Replace('\\', '/'));

    /// <summary>
    /// Undo `parkdir`: remove exactly the given dummy ids from every bundle under a root,
    /// verifying that bones/materials/meshes/layouts are untouched and that every
    /// remaining dummy entry kept its order and values.
    /// </summary>
    private static int StripDir(string root, string outRoot, string idArg, string nameFilter, bool dryRun)
    {
        s_quiet = true;
        var ids = new HashSet<short>(idArg.Split(',').Select(s => short.Parse(s.Trim(), CultureInfo.InvariantCulture)));
        bool inPlace = string.Equals(outRoot, "INPLACE", StringComparison.OrdinalIgnoreCase);
        string want = nameFilter.ToLowerInvariant();
        if (!want.EndsWith(".dcx")) want += ".dcx";
        var files = Directory.EnumerateFiles(root, "*", SearchOption.AllDirectories)
                             .Where(f => Path.GetFileName(f).ToLowerInvariant().EndsWith(want))
                             .OrderBy(f => f).ToList();
        Console.WriteLine($"stripdir: {files.Count} file(s) matching '{nameFilter}' under {root}"
                          + (dryRun ? "  (DRY RUN)" : inPlace ? "  (IN PLACE)" : $"  -> {outRoot}"));

        int cleaned = 0, already = 0, skipped = 0, failed = 0, removedTotal = 0;
        foreach (string f in files)
        {
            try
            {
                byte[] raw = File.ReadAllBytes(f);
                DCX.Type dcxType = DCX.Type.None;
                byte[] payload = DCX.Is(raw) ? DCX.Decompress(raw, out dcxType) : raw;
                BND4 bnd = BND4.Read(payload);

                BinderFile target = null;
                foreach (BinderFile bf in bnd.Files)
                    if (EntryName(bf).EndsWith(".flver", StringComparison.OrdinalIgnoreCase)) { target = bf; break; }
                if (target == null) { skipped++; continue; }

                FLVER2 flver = FLVER2.Read(target.Bytes);
                int gone = flver.Dummies.Count(d => ids.Contains(d.ReferenceID));
                if (gone == 0) { already++; continue; }

                string beforeBones = Digest(Bones(flver));
                string beforeMats = Digest(Materials(flver));
                string beforeMeshes = Digest(Meshes(flver));
                string beforeLayouts = Digest(Layouts(flver));
                int beforeCount = flver.Dummies.Count;
                var expected = flver.Dummies.Where(d => !ids.Contains(d.ReferenceID))
                                            .Select(d => (d.ReferenceID, d.ParentBoneIndex, d.AttachBoneIndex, d.Position)).ToList();

                flver.Dummies.RemoveAll(d => ids.Contains(d.ReferenceID));
                target.Bytes = flver.Write();
                byte[] newPayload = bnd.Write();
                byte[] outBytes = dcxType == DCX.Type.None ? newPayload : DCX.Compress(newPayload, dcxType);

                if (dryRun)
                {
                    Console.WriteLine($"  would strip {Path.GetFileName(f)}: -{gone} dummy(s) ({beforeCount} -> {flver.Dummies.Count})");
                    cleaned++;
                    removedTotal += gone;
                    continue;
                }

                DCX.Type t2;
                byte[] back = DCX.Is(outBytes) ? DCX.Decompress(outBytes, out t2) : outBytes;
                FLVER2 backFlver = null;
                foreach (BinderFile bf in BND4.Read(back).Files)
                    if (EntryName(bf).EndsWith(".flver", StringComparison.OrdinalIgnoreCase)) { backFlver = FLVER2.Read(bf.Bytes); break; }
                bool ok = backFlver != null && backFlver.Dummies.Count == flver.Dummies.Count &&
                          Digest(Bones(backFlver)) == beforeBones && Digest(Materials(backFlver)) == beforeMats &&
                          Digest(Meshes(backFlver)) == beforeMeshes && Digest(Layouts(backFlver)) == beforeLayouts;
                for (int i = 0; ok && i < expected.Count; ++i)
                {
                    var a = expected[i];
                    var b = backFlver.Dummies[i];
                    if (a.ReferenceID != b.ReferenceID || a.ParentBoneIndex != b.ParentBoneIndex ||
                        a.AttachBoneIndex != b.AttachBoneIndex || a.Position != b.Position) ok = false;
                }
                if (!ok)
                {
                    failed++;
                    Console.WriteLine($"  REJECTED {Path.GetFileName(f)}: structure changed -- left untouched");
                    continue;
                }

                string outPath = inPlace ? f : Path.Combine(outRoot, Path.GetFileName(f));
                if (!inPlace) Directory.CreateDirectory(outRoot);
                File.WriteAllBytes(outPath, outBytes);
                cleaned++;
                removedTotal += gone;
                Console.WriteLine($"  stripped {Path.GetFileName(f)}: -{gone} dummy(s) ({beforeCount} -> {flver.Dummies.Count}) {raw.Length} -> {outBytes.Length} bytes");
            }
            catch (Exception ex)
            {
                failed++;
                Console.WriteLine($"  FAILED {Path.GetFileName(f)}: {ex.Message}");
            }
        }
        Console.WriteLine($"summary: cleaned={cleaned} already-clean={already} no-flver={skipped} failed={failed} dummies-removed={removedTotal}");
        return failed > 0 ? 1 : 0;
    }

    /// <summary>
    /// Batch version of `park` for a whole game directory: give EVERY character model the
    /// parking dummies (appended; nothing vanilla is touched), so an NPC that resolves the
    /// shared parameter value also gets a valid dummy 1 km below the character instead of a
    /// degenerate matrix (black triangles / flicker).
    ///
    /// Each file is verified before it is written: bone list, materials, meshes and buffer
    /// layouts must be identical afterwards and the dummy table must be the old entries
    /// plus exactly the appended ones.  A file that fails is left untouched.
    /// </summary>
    private static int ParkDir(string root, string outRoot, string idArg, string posArg,
                               string parentArg, string nameFilter, bool dryRun)
    {
        s_quiet = true;
        var ids = idArg.Split(',').Select(s => short.Parse(s.Trim(), CultureInfo.InvariantCulture)).ToArray();
        int parentBone = int.Parse(parentArg, CultureInfo.InvariantCulture);
        float[] pos = posArg.Split(',').Select(s => float.Parse(s, CultureInfo.InvariantCulture)).ToArray();
        bool inPlace = string.Equals(outRoot, "INPLACE", StringComparison.OrdinalIgnoreCase);

        string want = nameFilter.ToLowerInvariant();
        if (!want.EndsWith(".dcx")) want += ".dcx";
        var files = Directory.EnumerateFiles(root, "*", SearchOption.AllDirectories)
                             .Where(f => Path.GetFileName(f).ToLowerInvariant().EndsWith(want))
                             .OrderBy(f => f).ToList();
        Console.WriteLine($"parkdir: {files.Count} file(s) matching '{nameFilter}' under {root}"
                          + (dryRun ? "  (DRY RUN)" : inPlace ? "  (IN PLACE)" : $"  -> {outRoot}"));

        int patched = 0, already = 0, skipped = 0, failed = 0, appended = 0;
        foreach (string f in files)
        {
            try
            {
                byte[] raw = File.ReadAllBytes(f);
                DCX.Type dcxType = DCX.Type.None;
                byte[] payload = DCX.Is(raw) ? DCX.Decompress(raw, out dcxType) : raw;
                BND4 bnd = BND4.Read(payload);

                BinderFile target = null;
                foreach (BinderFile bf in bnd.Files)
                    if (EntryName(bf).EndsWith(".flver", StringComparison.OrdinalIgnoreCase)) { target = bf; break; }
                if (target == null) { skipped++; continue; }

                FLVER2 flver = FLVER2.Read(target.Bytes);
                var have = new HashSet<short>(flver.Dummies.Select(d => d.ReferenceID));
                var missing = ids.Where(i => !have.Contains(i)).ToArray();
                if (missing.Length == 0) { already++; continue; }

                string beforeBones = Digest(Bones(flver));
                string beforeMats = Digest(Materials(flver));
                string beforeMeshes = Digest(Meshes(flver));
                string beforeLayouts = Digest(Layouts(flver));
                int beforeDummies = flver.Dummies.Count;
                var beforeList = flver.Dummies
                    .Select(d => (d.ReferenceID, d.ParentBoneIndex, d.AttachBoneIndex, d.Position)).ToList();

                FLVER.Dummy proto = flver.Dummies.FirstOrDefault(d => d.AttachBoneIndex < 0) ?? flver.Dummies[0];
                foreach (short id in missing)
                {
                    flver.Dummies.Add(new FLVER.Dummy
                    {
                        ReferenceID = id,
                        ParentBoneIndex = (short)parentBone,
                        AttachBoneIndex = -1,
                        Position = new System.Numerics.Vector3(pos[0], pos[1], pos[2]),
                        Forward = proto.Forward,
                        Upward = proto.Upward,
                        Color = proto.Color,
                        Flag1 = proto.Flag1,
                        UseUpwardVector = proto.UseUpwardVector,
                        Unk30 = proto.Unk30,
                        Unk34 = proto.Unk34,
                    });
                }
                target.Bytes = flver.Write();
                byte[] newPayload = bnd.Write();
                byte[] outBytes = dcxType == DCX.Type.None ? newPayload : DCX.Compress(newPayload, dcxType);

                if (dryRun)
                {
                    Console.WriteLine($"  would patch {Path.GetFileName(f)}: +{string.Join(",", missing)} ({beforeDummies} -> {flver.Dummies.Count} dummies)");
                    patched++;
                    appended += missing.Length;
                    continue;
                }

                // re-read what we are about to write and prove nothing else moved
                DCX.Type t2;
                byte[] back = DCX.Is(outBytes) ? DCX.Decompress(outBytes, out t2) : outBytes;
                BND4 backBnd = BND4.Read(back);
                FLVER2 backFlver = null;
                foreach (BinderFile bf in backBnd.Files)
                    if (EntryName(bf).EndsWith(".flver", StringComparison.OrdinalIgnoreCase)) { backFlver = FLVER2.Read(bf.Bytes); break; }
                if (backFlver == null || backFlver.Dummies.Count != flver.Dummies.Count ||
                    Digest(Bones(backFlver)) != beforeBones || Digest(Materials(backFlver)) != beforeMats ||
                    Digest(Meshes(backFlver)) != beforeMeshes || Digest(Layouts(backFlver)) != beforeLayouts)
                {
                    failed++;
                    Console.WriteLine($"  REJECTED {Path.GetFileName(f)}: structure changed -- left untouched");
                    continue;
                }
                bool vanillaIntact = true;
                for (int i = 0; i < beforeList.Count; i++)
                {
                    var a = beforeList[i];
                    var b = backFlver.Dummies[i];
                    if (a.ReferenceID != b.ReferenceID || a.ParentBoneIndex != b.ParentBoneIndex ||
                        a.AttachBoneIndex != b.AttachBoneIndex || a.Position != b.Position) { vanillaIntact = false; break; }
                }
                if (!vanillaIntact)
                {
                    failed++;
                    Console.WriteLine($"  REJECTED {Path.GetFileName(f)}: an existing dummy entry changed -- left untouched");
                    continue;
                }

                string outPath = inPlace ? f : Path.Combine(outRoot, Path.GetFileName(f));
                if (!inPlace) Directory.CreateDirectory(outRoot);
                File.WriteAllBytes(outPath, outBytes);
                patched++;
                appended += missing.Length;
                Console.WriteLine($"  patched {Path.GetFileName(f)}: +{string.Join(",", missing)} ({beforeDummies} -> {flver.Dummies.Count} dummies) {raw.Length} -> {outBytes.Length} bytes");
            }
            catch (Exception ex)
            {
                failed++;
                Console.WriteLine($"  FAILED {Path.GetFileName(f)}: {ex.Message}");
            }
        }
        Console.WriteLine($"summary: patched={patched} already-had={already} no-flver={skipped} failed={failed} dummies-appended={appended}");
        return failed > 0 ? 1 : 0;
    }

    private static int Dummies(string path)
    {
        BND4 bnd = ReadBundle(path, out _, out _);
        foreach (BinderFile f in bnd.Files)
        {
            string name = Path.GetFileName((f.Name ?? "").Replace('\\', '/'));
            if (!name.EndsWith(".flver", StringComparison.OrdinalIgnoreCase)) continue;
            FLVER2 flver;
            try { flver = FLVER2.Read(f.Bytes); }
            catch (Exception ex) { Console.WriteLine($"  {name}: FLVER read failed: {ex.Message}"); continue; }
            Console.WriteLine($"{name}: dummies={flver.Dummies.Count} bones={flver.Bones.Count} meshes={flver.Meshes.Count}");
            foreach (FLVER.Dummy d in flver.Dummies.OrderBy(x => x.ReferenceID))
            {
                string bone = (d.ParentBoneIndex >= 0 && d.ParentBoneIndex < flver.Bones.Count)
                    ? flver.Bones[d.ParentBoneIndex].Name : "?";
                string scale = (d.ParentBoneIndex >= 0 && d.ParentBoneIndex < flver.Bones.Count)
                    ? string.Format("scale=({0:0.###},{1:0.###},{2:0.###})", flver.Bones[d.ParentBoneIndex].Scale.X,
                                    flver.Bones[d.ParentBoneIndex].Scale.Y, flver.Bones[d.ParentBoneIndex].Scale.Z)
                    : "scale=?";
                double dist = Math.Sqrt(d.Position.X * d.Position.X + d.Position.Y * d.Position.Y + d.Position.Z * d.Position.Z);
                Console.WriteLine($"  dummy {d.ReferenceID,5}  bone[{d.ParentBoneIndex,3}] {bone,-26} pos=({d.Position.X,9:0.##},{d.Position.Y,9:0.##},{d.Position.Z,9:0.##}) |p|={dist,8:0.##} {scale} attachBone={d.AttachBoneIndex}");
            }
        }
        return 0;
    }

    private static int Inspect(string filter)    {
        Type[] types;
        try { types = typeof(TAE3).Assembly.GetTypes(); }
        catch (System.Reflection.ReflectionTypeLoadException ex) { types = ex.Types.Where(t => t != null).ToArray(); }
        foreach (Type t in types.Where(t => t.FullName != null && t.FullName.Contains(filter)))
        {
            Console.WriteLine("TYPE " + t.FullName + (t.IsAbstract ? " (abstract)" : ""));
            foreach (var c in t.GetConstructors(System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance))
                Console.WriteLine($"   ctor({string.Join(", ", c.GetParameters().Select(p => p.ParameterType.Name + " " + p.Name))}) [{(c.IsPublic ? "public" : "non-public")}]");
            foreach (var fi in t.GetFields(System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.DeclaredOnly))
                Console.WriteLine($"   field {fi.FieldType.Name} {fi.Name}");
            foreach (var p in t.GetProperties(System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.DeclaredOnly))
                Console.WriteLine($"   prop {p.PropertyType.Name} {p.Name}");
        }
        return 0;
    }

    /// <summary>Clone an existing event instance (the event classes have no public parameterless ctor).</summary>
    private static TAE3.Event CloneEvent(TAE3.Event proto)
    {
        var m = typeof(object).GetMethod("MemberwiseClone", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
        return (TAE3.Event)m.Invoke(proto, null);
    }

    private static int Validate(string[] paths)
    {
        foreach (string path in paths)
        {
            Console.WriteLine("=== " + path);
            BND4 bnd;
            try { bnd = ReadBundle(path, out _, out _); }
            catch (Exception ex) { Console.WriteLine("  FAILED: " + ex.Message); continue; }

            var taes = TaeEntries(bnd, out var errors);
            int anim = 0, hide = 0, mask = 0;
            var byParams = new SortedDictionary<string, int>();
            var leftOnly = new List<string>();
            foreach ((string name, BinderFile _, TAE3 tae) in taes)
            {
                foreach (TAE3.Animation a in tae.Animations)
                {
                    anim++;
                    foreach (TAE3.Event ev in a.Events)
                    {
                        if (ev.Type == TAE3.EventType.HideWeapon)
                        {
                            hide++;
                            string hex = Hex(ev);
                            byParams.TryGetValue(hex, out int n);
                            byParams[hex] = n + 1;
                            if (ev is TAE3.Event.HideWeapon hw && hw.Unk00 != 0)
                                leftOnly.Add($"{name} anim {a.ID} {hex} @{ev.StartTime:0.###}-{ev.EndTime:0.###}");
                        }
                        else if (ev.Type == TAE3.EventType.HideModelMask) mask++;
                    }
                }
            }
            Console.WriteLine($"  entries={bnd.Files.Count} taeFiles={taes.Count} taeErrors={errors.Count} animations={anim}");
            Console.WriteLine($"  HideWeapon(710)={hide}  HideModelMask(711)={mask}");
            foreach (var kv in byParams) Console.WriteLine($"    params [{kv.Key}] : {kv.Value}");
            foreach (var e in errors) Console.WriteLine($"    !! {e.Item1}: {e.Item2.Message}");
            foreach (string s in leftOnly.Take(3)) Console.WriteLine("    left-hide " + s);
        }
        return 0;
    }

    private static int Dump710(string path)
    {
        BND4 bnd = ReadBundle(path, out _, out _);
        var taes = TaeEntries(bnd, out var errors);
        foreach ((string name, BinderFile _, TAE3 tae) in taes)
        {
            foreach (TAE3.Animation a in tae.Animations)
            {
                foreach (TAE3.Event ev in a.Events)
                {
                    if (ev.Type == TAE3.EventType.HideWeapon)
                        Console.WriteLine($"{name,-12} anim {a.ID,-7} [{Hex(ev)}] @{ev.StartTime:0.###}-{ev.EndTime:0.###}");
                }
            }
        }
        foreach (var e in errors) Console.WriteLine($"!! {e.Item1}: {e.Item2.Message}");
        return 0;
    }

    private static int Add(string inPath, string outPath, string specPath)
    {
        BND4 bnd = ReadBundle(inPath, out _, out DCX.Type dcxType);
        byte[] original = File.ReadAllBytes(inPath);

        var wanted = new List<(string tae, long anim, byte[] pars, float start, float end)>();
        foreach (string rawLine in File.ReadAllLines(specPath))
        {
            string line = rawLine.Trim();
            if (line.Length == 0 || line.StartsWith("#")) continue;
            string[] p = line.Split('\t');
            if (p.Length < 3) p = line.Split(new[] { ' ', ',' }, StringSplitOptions.RemoveEmptyEntries);
            wanted.Add((
                Path.GetFileName(p[0].Trim()),
                long.Parse(p[1].Trim(), CultureInfo.InvariantCulture),
                ParseHex(p[2].Trim()),
                p.Length > 3 && p[3].Trim().Length > 0 ? float.Parse(p[3].Trim(), CultureInfo.InvariantCulture) : 0f,
                p.Length > 4 && p[4].Trim().Length > 0 ? float.Parse(p[4].Trim(), CultureInfo.InvariantCulture) : 999f));
        }
        Console.WriteLine($"spec: {wanted.Count} target(s) from {specPath}");

        // Event classes expose no public parameterless constructor, so clone an existing
        // HideWeapon event and rewrite its fields.
        TAE3.Event proto = null;
        foreach (BinderFile f0 in bnd.Files)
        {
            string n0 = Path.GetFileName((f0.Name ?? "").Replace('\\', '/'));
            if (!n0.EndsWith(".tae", StringComparison.OrdinalIgnoreCase)) continue;
            TAE3 t0;
            try { t0 = TAE3.Read(f0.Bytes); } catch { continue; }
            proto = t0.Animations.SelectMany(a => a.Events).FirstOrDefault(e => e.Type == TAE3.EventType.HideWeapon);
            if (proto != null) break;
        }
        if (proto == null) { Console.WriteLine("ERROR: no existing HideWeapon event in this bundle to clone"); return 1; }
        Console.WriteLine($"  prototype HideWeapon event found (clone source)");

        int added = 0, touched = 0;
        foreach (BinderFile f in bnd.Files)
        {
            string name = Path.GetFileName((f.Name ?? "").Replace('\\', '/'));
            if (!name.EndsWith(".tae", StringComparison.OrdinalIgnoreCase)) continue;
            var mine = wanted.Where(w => string.Equals(w.tae, name, StringComparison.OrdinalIgnoreCase)).ToList();
            if (mine.Count == 0) continue;

            TAE3 tae = TAE3.Read(f.Bytes);
            bool dirty = false;
            foreach ((string _, long animId, byte[] pars, float start, float end) in mine)
            {
                foreach (TAE3.Animation a in tae.Animations)
                {
                    if (a.ID != animId) continue;
                    bool exists = a.Events.Any(e => e.Type == TAE3.EventType.HideWeapon &&
                                                    e is TAE3.Event.HideWeapon hw &&
                                                    hw.Unk00 == pars[0] && hw.Unk01 == pars[1] &&
                                                    hw.Unk02 == pars[2] && hw.Unk03 == pars[3]);
                    if (exists)
                    {
                        Console.WriteLine($"  {name} anim {animId}: already has [{string.Join(" ", pars.Select(b => b.ToString("x2")))}] - skipped");
                        continue;
                    }
                    var ev = (TAE3.Event.HideWeapon)CloneEvent(proto);
                    ev.StartTime = start;
                    ev.EndTime = end;
                    ev.Unk00 = pars[0];
                    ev.Unk01 = pars[1];
                    ev.Unk02 = pars[2];
                    ev.Unk03 = pars[3];
                    a.Events.Add(ev);
                    added++;
                    dirty = true;
                    Console.WriteLine($"  {name} anim {animId}: +[ {string.Join(" ", pars.Select(b => b.ToString("x2")))} ] @{start}-{end} (events now {a.Events.Count}, groups {a.EventGroups.Count})");
                }
            }
            if (dirty) { f.Bytes = tae.Write(); touched++; }
        }

        byte[] outBytes = WriteBundle(bnd, original, dcxType);
        File.WriteAllBytes(outPath, outBytes);
        Console.WriteLine($"wrote {outPath}: {outBytes.Length} bytes, events added={added}, tae files touched={touched}");
        if (added == 0) return 1;

        BND4 back = ReadBundle(outPath, out _, out _);
        var taes = TaeEntries(back, out var errors);
        int found = taes.Sum(t => t.tae.Animations.Sum(a => a.Events.Count(e => e.Type == TAE3.EventType.HideWeapon)));
        Console.WriteLine($"  verify: re-read ok, HideWeapon events now {found}, taeErrors={errors.Count}");
        return 0;
    }

    private static int RoundTrip(string inPath, string outPath)
    {
        BND4 bnd = ReadBundle(inPath, out byte[] payload, out DCX.Type dcxType);
        byte[] original = File.ReadAllBytes(inPath);
        byte[] outBytes = WriteBundle(bnd, original, dcxType);
        File.WriteAllBytes(outPath, outBytes);
        Console.WriteLine($"roundtrip: payload {payload.Length}, file {original.Length} -> {outBytes.Length}");
        BND4 again = ReadBundle(outPath, out _, out _);
        var taes = TaeEntries(again, out var errors);
        Console.WriteLine($"  re-read ok: {again.Files.Count} entries, {taes.Count} TAE, errors={errors.Count}");
        return 0;
    }

    private static byte[] ParseHex(string hex)
    {
        hex = hex.Replace(" ", "").Replace("0x", "");
        var b = new byte[hex.Length / 2];
        for (int i = 0; i < b.Length; i++) b[i] = Convert.ToByte(hex.Substring(i * 2, 2), 16);
        return b;
    }
}
