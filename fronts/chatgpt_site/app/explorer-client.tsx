"use client";

import {
  type FormEvent,
  useRef,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

type Kpi = {
  commune: string;
  insee_code: string;
  code_postal?: string;
  department: string;
  year: number;
  transaction_count: number;
  median_price?: number | null;
  median_price_per_m2?: number | null;
  p25_price_per_m2?: number | null;
  p75_price_per_m2?: number | null;
  median_surface?: number | null;
};

type Place = {
  label: string;
  kind: "commune" | "section";
  insee_code: string;
  department: string;
  code_postal?: string;
  section?: string;
  latitude?: number;
  longitude?: number;
};

type Manifest = {
  contract_version: string;
  generated_at: string;
  kpis: string;
  search_index: string;
  departments: Record<string, { details: string | Record<string, string>; sections?: string }>;
  kpi_files?: Record<string, string>;
  search_files?: Record<string, string>;
  snapshots?: Record<string, { version: number; raw_source?: string; details: Record<string, string> }>;
  snapshot_history?: Record<string, Array<{ version: number; raw_source?: string; details: Record<string, string> }>>;
  row_history?: string[];
};

type ExportData = {
  national?: Kpi[];
  departments?: Kpi[];
  communes?: Kpi[];
};

type Sale = Record<string, unknown>;
type Tab = "kpis" | "details";
type ResultsView = "split" | "list" | "map";
type KpiSort = "commune" | "transaction_count" | "median_price" | "median_price_per_m2" | "median_surface";
type Filters = {
  from: string;
  to: string;
  minPrice: string;
  maxPrice: string;
  minSurface: string;
  maxSurface: string;
  minLand: string;
  maxLand: string;
  rooms: string;
  localType: string;
  mutation: string;
  department: string;
  postalCode: string;
  address: string;
};

const EMPTY_FILTERS: Filters = {
  from: "",
  to: "",
  minPrice: "",
  maxPrice: "",
  minSurface: "",
  maxSurface: "",
  minLand: "",
  maxLand: "",
  rooms: "",
  localType: "",
  mutation: "",
  department: "",
  postalCode: "",
  address: "",
};

type SortColumn = "date_mutation" | "commune" | "nature_mutation" | "type_local" | "nombre_pieces_principales" | "surface_reelle_bati" | "surface_terrain" | "valeur_fonciere" | "price_per_m2";
const SORT_COLUMNS: Array<{ key: SortColumn; label: string }> = [
  { key: "date_mutation", label: "Date" }, { key: "commune", label: "Commune" },
  { key: "nature_mutation", label: "Mutation" }, { key: "type_local", label: "Bien" },
  { key: "nombre_pieces_principales", label: "Pièces" }, { key: "surface_reelle_bati", label: "Surface" },
  { key: "surface_terrain", label: "Terrain" }, { key: "price_per_m2", label: "€/m²" }, { key: "valeur_fonciere", label: "Prix" },
];

let databasePromise: Promise<import("@duckdb/duckdb-wasm").AsyncDuckDB> | null = null;

async function getDatabase() {
  if (!databasePromise) {
    databasePromise = (async () => {
      const duckdb = await import("@duckdb/duckdb-wasm");
      const bundle = await duckdb.selectBundle(duckdb.getJsDelivrBundles());
      if (!bundle.mainWorker || !bundle.mainModule) throw new Error("DuckDB-WASM n’a pas pu démarrer.");
      const workerUrl = URL.createObjectURL(new Blob(
        [`importScripts("${bundle.mainWorker}");`],
        { type: "text/javascript" },
      ));
      const worker = new Worker(workerUrl);
      const database = new duckdb.AsyncDuckDB(new duckdb.ConsoleLogger(), worker);
      try {
        await database.instantiate(bundle.mainModule, bundle.pthreadWorker);
      } finally {
        URL.revokeObjectURL(workerUrl);
      }
      return database;
    })().catch((error) => {
      databasePromise = null;
      throw error;
    });
  }
  return databasePromise;
}

function number(value: unknown) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 }).format(value);
}

function euro(value: unknown) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(value);
}

function quoteSql(value: string) {
  return value.replaceAll("'", "''");
}

function sqlNumber(value: string) {
  const parsed = Number(value.replace(",", "."));
  return Number.isFinite(parsed) && parsed >= 0 ? String(parsed) : "";
}

function csvCell(value: unknown) {
  const text = value == null ? "" : String(value);
  return `"${text.replaceAll('"', '""')}"`;
}

function isDate(value: string) {
  return /^\d{4}-\d{2}-\d{2}$/.test(value);
}

function validateFilters(filters: Filters) {
  if (filters.from && !isDate(filters.from)) return "La date de début est invalide.";
  if (filters.to && !isDate(filters.to)) return "La date de fin est invalide.";
  if (filters.from && filters.to && filters.from > filters.to) return "La date de début doit précéder la date de fin.";
  const ranges = [
    ["le prix", filters.minPrice, filters.maxPrice],
    ["la surface bâtie", filters.minSurface, filters.maxSurface],
    ["la surface du terrain", filters.minLand, filters.maxLand],
  ] as const;
  for (const [label, minimum, maximum] of ranges) {
    for (const value of [minimum, maximum]) {
      if (value && (sqlNumber(value) === "" || !Number.isFinite(Number(value.replace(",", "."))))) {
        return `Valeur incorrecte pour ${label} : saisissez un nombre positif.`;
      }
    }
    if (minimum && maximum && Number(minimum.replace(",", ".")) > Number(maximum.replace(",", "."))) {
      return `La valeur minimale de ${label} doit être inférieure à sa valeur maximale.`;
    }
  }
  if (filters.postalCode && !/^\d{5}$/.test(filters.postalCode.trim())) return "Saisissez un code postal à cinq chiffres.";
  return "";
}

function TransactionMap({
  sales,
  center,
  onSelect,
}: {
  sales: Sale[];
  center?: [number, number];
  onSelect: (sale: Sale) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let map: import("leaflet").Map | null = null;
    let cancelled = false;
    (async () => {
      if (!host.current) return;
      const L = await import("leaflet");
      await import("leaflet.markercluster");
      if (cancelled || !host.current) return;
      map = L.map(host.current, { scrollWheelZoom: false }).setView(center ?? [46.6, 2.4], center ? 12 : 5);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "© OpenStreetMap contributors",
      }).addTo(map);
      const cluster = L.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 45 });
      for (const sale of sales) {
        if (sale.latitude == null || sale.longitude == null) continue;
        const latitude = Number(sale.latitude);
        const longitude = Number(sale.longitude);
        if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) continue;
        const marker = L.circleMarker([latitude, longitude], {
          radius: 6,
          color: "#064e3b",
          weight: 1,
          fillColor: "#34d399",
          fillOpacity: 0.9,
        }).bindPopup(`${String(sale.date_mutation ?? "")} · ${euro(sale.valeur_fonciere)}`);
        marker.on("click", () => onSelect(sale));
        cluster.addLayer(marker);
      }
      map.addLayer(cluster);
    })();
    return () => {
      cancelled = true;
      map?.remove();
    };
  }, [center, onSelect, sales]);
  return <div ref={host} className="h-[360px] w-full rounded-lg bg-slate-100" aria-label="Carte des transactions géolocalisées" />;
}

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(response.status === 404 || response.status === 503
    ? "Les données ne sont pas encore publiées."
    : `Erreur lors du chargement (${response.status}).`);
  if (path.endsWith(".json.gz")) {
    if (typeof DecompressionStream === "undefined") throw new Error("La décompression gzip n’est pas disponible dans ce navigateur.");
    const body = response.body?.pipeThrough(new DecompressionStream("gzip"));
    if (!body) throw new Error("Le bundle de données compressé est vide.");
    return JSON.parse(await new Response(body).text()) as T;
  }
  return response.json() as Promise<T>;
}

export default function ExplorerClient() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [kpis, setKpis] = useState<ExportData>({});
  const [places, setPlaces] = useState<Place[]>([]);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "empty" | "error">("loading");
  const [loadMessage, setLoadMessage] = useState("");
  const [query, setQuery] = useState("");
  const [place, setPlace] = useState<Place | null>(null);
  const [year, setYear] = useState("all");
  const [department, setDepartment] = useState("all");
  const [tab, setTab] = useState<Tab>("kpis");
  const [resultsView, setResultsView] = useState<ResultsView>("split");
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<Filters>(EMPTY_FILTERS);
  const [sales, setSales] = useState<Sale[]>([]);
  const [queryFiles, setQueryFiles] = useState<string[]>([]);
  const [queryPredicate, setQueryPredicate] = useState("");
  const [hasSearched, setHasSearched] = useState(false);
  const [selectedSale, setSelectedSale] = useState<Sale | null>(null);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(50);
  const [communeQuery, setCommuneQuery] = useState("");
  const [communePage, setCommunePage] = useState(0);
  const [communePageSize, setCommunePageSize] = useState(100);
  const [communeSort, setCommuneSort] = useState<{ column: KpiSort; direction: "ASC" | "DESC" }>({ column: "transaction_count", direction: "DESC" });
  const [sort, setSort] = useState<{ column: SortColumn; direction: "ASC" | "DESC" }>({ column: "date_mutation", direction: "DESC" });
  const [resultCount, setResultCount] = useState<number | null>(null);
  const [querying, setQuerying] = useState(false);
  const [duckError, setDuckError] = useState("");
  const [banPlaces, setBanPlaces] = useState<Place[]>([]);
  const [urlHydrated, setUrlHydrated] = useState(false);
  const popNavigationRef = useRef(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const nextFilters = { ...EMPTY_FILTERS };
    for (const key of Object.keys(EMPTY_FILTERS) as Array<keyof Filters>) {
      nextFilters[key] = params.get(key) ?? "";
    }
    const requestedYear = params.get("year");
    if (requestedYear) setYear(requestedYear);
    const requestedDepartment = params.get("department");
    if (requestedDepartment) setDepartment(requestedDepartment);
    const requestedTab = params.get("tab");
    if (requestedTab === "details" || requestedTab === "kpis") setTab(requestedTab);
    setHasSearched(params.get("searched") === "1");
    const requestedView = params.get("view");
    if (requestedView === "list" || requestedView === "map" || requestedView === "split") setResultsView(requestedView);
    const requestedPage = Number(params.get("page"));
    if (Number.isInteger(requestedPage) && requestedPage >= 0) setPage(requestedPage);
    const requestedSize = Number(params.get("size"));
    if ([25, 50, 100].includes(requestedSize)) setPageSize(requestedSize);
    const requestedSort = params.get("sort") as SortColumn | null;
    if (requestedSort && SORT_COLUMNS.some((column) => column.key === requestedSort)) {
      setSort({ column: requestedSort, direction: params.get("dir") === "ASC" ? "ASC" : "DESC" });
    }
    setFilters(nextFilters);
    setAppliedFilters(nextFilters);
    setUrlHydrated(true);
  }, []);

  useEffect(() => {
    if (!urlHydrated) return;
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(appliedFilters)) if (value) params.set(key, value);
    params.set("year", year);
    params.set("department", department);
    params.set("tab", tab);
    params.set("view", resultsView);
    params.set("size", String(pageSize));
    params.set("page", String(page));
    params.set("sort", sort.column);
    params.set("dir", sort.direction);
    params.set("searched", hasSearched ? "1" : "0");
    const currentUrl = new URLSearchParams(window.location.search);
    const placeCode = place?.insee_code ?? currentUrl.get("place");
    const saleKey = selectedSale?.mutation_key ?? currentUrl.get("sale");
    if (placeCode) params.set("place", placeCode);
    if (saleKey) params.set("sale", String(saleKey));
    const search = params.toString();
    if (window.location.search !== `?${search}`) {
      if (popNavigationRef.current) window.history.replaceState(null, "", `${window.location.pathname}?${search}`);
      else window.history.pushState(null, "", `${window.location.pathname}?${search}`);
    }
    popNavigationRef.current = false;
  }, [appliedFilters, department, hasSearched, page, pageSize, place, resultsView, selectedSale, sort, tab, urlHydrated, year]);

  useEffect(() => {
    const restore = () => {
      popNavigationRef.current = true;
      const params = new URLSearchParams(window.location.search);
      const restoredFilters = { ...EMPTY_FILTERS };
      for (const key of Object.keys(EMPTY_FILTERS) as Array<keyof Filters>) restoredFilters[key] = params.get(key) ?? "";
      setFilters(restoredFilters);
      setAppliedFilters(restoredFilters);
      setYear(params.get("year") ?? "all");
      setDepartment(params.get("department") ?? "all");
      const restoredTab = params.get("tab");
      if (restoredTab === "details" || restoredTab === "kpis") setTab(restoredTab);
      const restoredView = params.get("view");
      if (restoredView === "split" || restoredView === "list" || restoredView === "map") setResultsView(restoredView);
      const restoredPage = Number(params.get("page"));
      setPage(Number.isInteger(restoredPage) && restoredPage >= 0 ? restoredPage : 0);
      const restoredSize = Number(params.get("size"));
      if ([25, 50, 100].includes(restoredSize)) setPageSize(restoredSize);
      const restoredSort = params.get("sort") as SortColumn | null;
      if (restoredSort && SORT_COLUMNS.some((column) => column.key === restoredSort)) setSort({ column: restoredSort, direction: params.get("dir") === "ASC" ? "ASC" : "DESC" });
      setPlace(null);
      setSelectedSale(null);
      setQueryFiles([]);
      setHasSearched(params.get("searched") === "1");
      restoredQueryRan.current = false;
    };
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, []);

  useEffect(() => {
    const wanted = new URLSearchParams(window.location.search).get("place");
    if (!wanted || place || !places.length) return;
    const found = places.find((item) => item.insee_code === wanted && item.kind === "commune");
    if (found) setPlace(found);
  }, [places, place]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const nextManifest = await fetchJson<Manifest>("/api/data/manifest.json");
        const [kpiIndex, searchIndex] = await Promise.all([
          fetchJson<Record<string, string> | ExportData>(`/api/data/${nextManifest.kpis}`),
          fetchJson<Record<string, string> | { places: Place[] }>(`/api/data/${nextManifest.search_index}`),
        ]);
        const legacyKpis = Array.isArray((kpiIndex as ExportData).national);
        const legacySearch = Array.isArray((searchIndex as { places?: unknown }).places);
        const kpiPaths = legacyKpis ? [] : Object.values(kpiIndex as Record<string, string>);
        const searchPaths = legacySearch ? [] : Object.values(searchIndex as Record<string, string>);
        const [kpiBundles, searchBundles] = await Promise.all([
          Promise.all(kpiPaths.map((path) => fetchJson<ExportData>(`/api/data/${path}`))),
          Promise.all(searchPaths.map((path) => fetchJson<{ places: Place[] }>(`/api/data/${path}`))),
        ]);
        const nextKpis: ExportData = legacyKpis ? kpiIndex as ExportData : {
          national: kpiBundles.flatMap((bundle) => bundle.national ?? []),
          departments: kpiBundles.flatMap((bundle) => bundle.departments ?? []),
          communes: kpiBundles.flatMap((bundle) => bundle.communes ?? []),
        };
        nextKpis.national?.sort((left, right) => right.year - left.year);
        nextKpis.communes?.sort((left, right) => right.year - left.year || left.commune.localeCompare(right.commune, "fr"));
        const placesByKey = new Map<string, Place>();
        const indexedPlaces: Place[] = legacySearch
          ? (searchIndex as { places: Place[] }).places
          : searchBundles.flatMap((bundle) => bundle.places ?? []);
        for (const item of indexedPlaces) {
          placesByKey.set(`${item.kind}:${item.insee_code}:${item.section ?? ""}`, item);
        }
        if (cancelled) return;
        setManifest(nextManifest);
        const urlYear = new URLSearchParams(window.location.search).get("year");
        if (!urlYear) setYear(Object.keys(nextManifest.kpi_files ?? {}).sort((a, b) => Number(b) - Number(a))[0] ?? "all");
        setKpis(nextKpis);
        setPlaces(Array.from(placesByKey.values()));
        setLoadState("ready");
      } catch (error) {
        if (cancelled) return;
        const message = error instanceof Error ? error.message : "Chargement impossible.";
        setLoadMessage(message);
        setLoadState(message.includes("pas encore publiées") ? "empty" : "error");
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const national = useMemo(() => {
    if (year !== "all") return kpis.national?.find((item) => String(item.year) === year);
    const rows = kpis.national ?? [];
    if (!rows.length) return undefined;
    return { ...rows[0], year: 0, transaction_count: rows.reduce((total, row) => total + row.transaction_count, 0), median_price: null, median_price_per_m2: null, median_surface: null };
  }, [kpis.national, year]);
  const visibleCommunes = useMemo(() => {
    const yearFiltered = year === "all" ? (kpis.communes ?? [])
      : (kpis.communes ?? []).filter((item) => String(item.year) === year);
    const source = place
      ? yearFiltered.filter((item) => item.insee_code === place.insee_code)
      : yearFiltered;
    const term = communeQuery.trim().toLocaleLowerCase("fr");
    const filtered = source.filter((item) => !term || item.commune.toLocaleLowerCase("fr").includes(term)
      || item.insee_code.includes(term) || (item.code_postal ?? "").includes(term));
    filtered.sort((left, right) => {
      const a = left[communeSort.column];
      const b = right[communeSort.column];
      const compared = typeof a === "string" && typeof b === "string"
        ? a.localeCompare(b, "fr")
        : Number(a ?? 0) - Number(b ?? 0);
      return communeSort.direction === "ASC" ? compared : -compared;
    });
    return filtered.slice(communePage * communePageSize, (communePage + 1) * communePageSize);
  }, [communePage, communePageSize, communeQuery, communeSort, kpis.communes, place, year]);
  const communeCount = useMemo(() => (kpis.communes ?? []).filter((item) =>
    (year === "all" || String(item.year) === year) && (!place || item.insee_code === place.insee_code)
    && (!communeQuery.trim() || item.commune.toLocaleLowerCase("fr").includes(communeQuery.trim().toLocaleLowerCase("fr"))
      || item.insee_code.includes(communeQuery.trim()) || (item.code_postal ?? "").includes(communeQuery.trim())),
  ).length, [communeQuery, kpis.communes, place, year]);
  const availableYears = useMemo(() => Array.from(new Set(
    (kpis.communes ?? []).map((item) => String(item.year)),
  )).sort((a, b) => Number(b) - Number(a)), [kpis.communes]);

  const matches = useMemo(() => {
    const term = query.trim().toLocaleLowerCase("fr");
    if (!term) return [];
    return places.filter((item) =>
      item.label.toLocaleLowerCase("fr").includes(term)
      || (item.code_postal ?? "").includes(term)
      || (item.section ?? "").toLocaleLowerCase("fr").includes(term),
    ).slice(0, 8);
  }, [places, query]);

  const runDetailsQuery = useCallback(async (
    nextPage: number,
    nextFilters: Filters,
    nextSort = sort,
    nextPageSize = pageSize,
  ) => {
    if (!manifest) return;
    restoredQueryRan.current = true;
    setHasSearched(true);
    const scopedDepartment = place?.department ?? (nextFilters.department || department);
    const selectedDepartments = scopedDepartment === "all"
      ? Object.keys(manifest.departments)
      : [scopedDepartment];
    const sources = selectedDepartments.flatMap((code) => {
      const details = manifest.departments[code]?.details;
      return typeof details === "string" ? [details] : year === "all"
        ? Object.values(details ?? {})
        : [details?.[year]].filter((item): item is string => Boolean(item));
    });
    if (!sources.length) {
      setDuckError("Aucun fichier de détail n’est disponible pour ce département.");
      return;
    }
    setQuerying(true);
    setDuckError("");
    try {
      const duckdb = await import("@duckdb/duckdb-wasm");
      const database = await getDatabase();
      const connection = await database.connect();
      const fileNames = sources.map((source, index) => `dvf-${year}-${index}-${source.split("/").at(-1) ?? "data"}`);
      await Promise.all(sources.map((source, index) => {
        const url = new URL(`/api/data/${source}`, window.location.origin).toString();
        return database.registerFileURL(fileNames[index], url, duckdb.DuckDBDataProtocol.HTTP, false);
      }));

      const conditions: string[] = [];
      if (place) conditions.push(`insee_code = '${quoteSql(place.insee_code)}'`);
      if (nextFilters.department || department !== "all") {
        const selected = nextFilters.department || department;
        if (selected !== "all") conditions.push(`code_departement = '${quoteSql(selected)}'`);
      }
      if (nextFilters.postalCode.trim()) conditions.push(`code_postal = '${quoteSql(nextFilters.postalCode.trim())}'`);
      if (nextFilters.address.trim()) conditions.push(`concat_ws(' ', no_voie, btq, type_voie, voie) ILIKE '%${quoteSql(nextFilters.address.trim())}%'`);
      if (nextFilters.from && isDate(nextFilters.from)) conditions.push(`date_mutation >= DATE '${nextFilters.from}'`);
      if (nextFilters.to && isDate(nextFilters.to)) conditions.push(`date_mutation <= DATE '${nextFilters.to}'`);
      if (year !== "all" && /^\d{4}$/.test(year)) conditions.push(`EXTRACT(YEAR FROM date_mutation) = ${Number(year)}`);
      if (sqlNumber(nextFilters.minPrice)) conditions.push(`valeur_fonciere >= ${sqlNumber(nextFilters.minPrice)}`);
      if (sqlNumber(nextFilters.maxPrice)) conditions.push(`valeur_fonciere <= ${sqlNumber(nextFilters.maxPrice)}`);
      if (sqlNumber(nextFilters.minSurface)) conditions.push(`surface_reelle_bati >= ${sqlNumber(nextFilters.minSurface)}`);
      if (sqlNumber(nextFilters.maxSurface)) conditions.push(`surface_reelle_bati <= ${sqlNumber(nextFilters.maxSurface)}`);
      if (sqlNumber(nextFilters.minLand)) conditions.push(`surface_terrain >= ${sqlNumber(nextFilters.minLand)}`);
      if (sqlNumber(nextFilters.maxLand)) conditions.push(`surface_terrain <= ${sqlNumber(nextFilters.maxLand)}`);
      if (nextFilters.rooms && /^\d+$/.test(nextFilters.rooms)) {
        conditions.push(nextFilters.rooms === "6"
          ? "nombre_pieces_principales >= 6"
          : `nombre_pieces_principales = ${Number(nextFilters.rooms)}`);
      }
      if (nextFilters.localType) conditions.push(`type_local = '${quoteSql(nextFilters.localType)}'`);
      if (nextFilters.mutation) conditions.push(`nature_mutation = '${quoteSql(nextFilters.mutation)}'`);

      const parquetFiles = `[${fileNames.map((name) => `'${quoteSql(name)}'`).join(",")}]`;
      const where = conditions.length ? `WHERE ${conditions.join(" AND ")}` : "";
      setQueryFiles(fileNames);
      setQueryPredicate(where);
      const orderColumn = nextSort.column === "price_per_m2"
        ? "valeur_fonciere / NULLIF(surface_reelle_bati, 0)"
        : nextSort.column;
      const sql = `SELECT date_mutation, nature_mutation, valeur_fonciere, commune,
          code_departement, code_postal, insee_code, no_voie, btq, type_voie, voie,
          prefixe_section, section, no_plan, no_disposition, type_local, surface_reelle_bati,
          surface_terrain, nombre_pieces_principales,
          valeur_fonciere / NULLIF(surface_reelle_bati, 0) AS price_per_m2,
          mutation_key, status, flag, latitude, longitude,
          count(*) OVER() AS _total
        FROM read_parquet(${parquetFiles}, union_by_name=true) ${where}
        ORDER BY ${orderColumn} ${nextSort.direction} NULLS LAST, mutation_key ASC
        LIMIT ${nextPageSize + 1} OFFSET ${nextPage * nextPageSize}`;
      try {
        const result = await connection.query(sql);
        const records = result.toArray().map((item) => item.toJSON() as Sale);
        setResultCount(records.length ? Number(records[0]._total) : nextPage === 0 ? 0 : resultCount);
        setSales(records.slice(0, nextPageSize));
        setPage(nextPage);
        const wantedSale = nextPage === 0 ? new URLSearchParams(window.location.search).get("sale") : null;
        setSelectedSale(records.find((record) => String(record.mutation_key ?? "") === wantedSale) ?? records[0] ?? null);
      } finally {
        await connection.close();
      }
    } catch (error) {
      setDuckError(error instanceof Error ? error.message : "La requête locale a échoué.");
    } finally {
      setQuerying(false);
    }
  }, [department, manifest, pageSize, place, resultCount, sort, year]);

  const restoredQueryRan = useRef(false);
  useEffect(() => {
    if (!hasSearched || !urlHydrated || !manifest || restoredQueryRan.current) return;
    const requestedPlace = new URLSearchParams(window.location.search).get("place");
    if (requestedPlace && !place) return;
    restoredQueryRan.current = true;
    void runDetailsQuery(page, appliedFilters);
  }, [appliedFilters, hasSearched, manifest, page, place, runDetailsQuery, urlHydrated]);

  async function searchAddress(event: FormEvent) {
    event.preventDefault();
    if (!query.trim()) return;
    if (matches.length) {
      choosePlace(matches[0]);
      return;
    }
    try {
      const url = new URL("https://api-adresse.data.gouv.fr/search/");
      url.searchParams.set("q", query.trim());
      url.searchParams.set("limit", "5");
      const response = await fetch(url);
      if (!response.ok) throw new Error("La recherche d’adresse est indisponible.");
      const result = await response.json() as {
        features?: Array<{ properties?: Record<string, unknown>; geometry?: { coordinates?: number[] } }>;
      };
      const found = (result.features ?? []).map((feature): Place => {
        const properties = feature.properties ?? {};
        const cityCode = String(properties.citycode ?? "");
        return {
          label: String(properties.label ?? "Adresse"),
          kind: "commune",
          insee_code: String(properties.citycode ?? ""),
          department: cityCode.startsWith("97") ? cityCode.slice(0, 3) : cityCode.slice(0, 2),
          code_postal: String(properties.postcode ?? ""),
          longitude: feature.geometry?.coordinates?.[0],
          latitude: feature.geometry?.coordinates?.[1],
        };
      }).filter((item) => item.insee_code && item.department);
      setBanPlaces(found);
      if (found.length === 1) choosePlace(found[0]);
    } catch (error) {
      setDuckError(error instanceof Error ? error.message : "La recherche d’adresse a échoué.");
    }
  }

  function choosePlace(next: Place) {
    setPlace(next);
    setQuery(next.label);
    setTab("kpis");
    setSales([]);
    setQueryFiles([]);
    setQueryPredicate("");
    setHasSearched(false);
    setSelectedSale(null);
    setBanPlaces([]);
    setPage(0);
    setDepartment(next.department);
    setResultCount(null);
    setFilters((current) => ({ ...current, department: "" }));
    setAppliedFilters((current) => ({ ...current, department: "" }));
  }

  function clearPlace() {
    setPlace(null);
    setQuery("");
    setDepartment("all");
    setSales([]);
    setQueryFiles([]);
    setQueryPredicate("");
    setHasSearched(false);
    setSelectedSale(null);
    setPage(0);
    setResultCount(null);
  }

  async function exportCsv() {
    if (!sales.length) return;
    if (!queryFiles.length) return;
    if ((resultCount ?? 0) > 100_000 && !window.confirm(`Cette exportation contient environ ${number(resultCount)} lignes et peut être volumineuse. Continuer ?`)) return;
    setQuerying(true);
    setDuckError("");
    try {
      const duckdb = await import("@duckdb/duckdb-wasm");
      const database = await getDatabase();
      const connection = await database.connect();
      try {
        const parquetFiles = `[${queryFiles.map((name) => `'${quoteSql(name)}'`).join(",")}]`;
        const exportOrder = sort.column === "price_per_m2" ? "valeur_fonciere / NULLIF(surface_reelle_bati, 0)" : sort.column;
        const result = await connection.query(`SELECT *, valeur_fonciere / NULLIF(surface_reelle_bati, 0) AS price_per_m2 FROM read_parquet(${parquetFiles}, union_by_name=true) ${queryPredicate} ORDER BY ${exportOrder} ${sort.direction} NULLS LAST, mutation_key ASC`);
        const records = result.toArray().map((item) => item.toJSON() as Sale);
        if (!records.length) return;
        const columns = Object.keys(records[0]).filter((column) => !column.startsWith("_"));
        const chunks = ["\uFEFF", columns.map(csvCell).join(",") + "\r\n"];
        for (let offset = 0; offset < records.length; offset += 2000) {
          chunks.push(records.slice(offset, offset + 2000).map((row) => columns.map((column) => csvCell(row[column])).join(",")).join("\r\n") + "\r\n");
        }
        const url = URL.createObjectURL(new Blob(chunks, { type: "text/csv;charset=utf-8" }));
        const link = document.createElement("a");
        link.href = url;
        link.download = `dvf-${place?.insee_code ?? department}-${year}.csv`;
        link.click();
        URL.revokeObjectURL(url);
      } finally { await connection.close(); }
    } catch (error) {
      setDuckError(error instanceof Error ? `Export impossible : ${error.message}` : "Export CSV impossible.");
    } finally { setQuerying(false); }
  }

  function setFilter<K extends keyof Filters>(key: K, value: Filters[K]) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  const selectSale = useCallback((sale: Sale) => setSelectedSale(sale), []);
  const mapCenter: [number, number] | undefined = place?.latitude !== undefined && place.longitude !== undefined
    ? [place.latitude, place.longitude]
    : undefined;

  const placeLabel = place?.label ?? "Toute la France";

  return (
    <main className="min-h-screen bg-[#f4f6f5] text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-[1480px] flex-wrap items-center gap-5 px-5 py-4 lg:px-10">
          <a className="flex items-center gap-3 font-semibold tracking-tight" href="/">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-emerald-950 text-sm font-bold text-emerald-50">DVF</span>
            <span className="text-lg">Explorer <span className="font-normal text-slate-400">/ France</span></span>
          </a>
          <form className="relative ml-auto flex min-w-[min(100%,520px)] flex-1 gap-2" onSubmit={searchAddress}>
            <label className="sr-only" htmlFor="place-search">Commune, code postal, section ou adresse</label>
            <input
              id="place-search"
              className="h-11 min-w-0 flex-1 rounded-lg border border-slate-300 bg-slate-50 px-4 text-sm outline-none transition focus:border-emerald-700 focus:bg-white focus:ring-2 focus:ring-emerald-700/15"
              placeholder="Commune, code postal, section ou adresse"
              value={query}
              onChange={(event) => { setQuery(event.target.value); setBanPlaces([]); }}
            />
            <button className="rounded-lg bg-emerald-950 px-5 text-sm font-semibold text-white hover:bg-emerald-800" type="submit">Rechercher</button>
            {place && <button type="button" onClick={clearPlace} className="rounded-lg border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700">Effacer</button>}
            {matches.length > 0 && query !== place?.label && (
              <div className="absolute left-0 right-24 top-12 z-20 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl">
                {matches.map((item) => (
                  <button key={`${item.kind}-${item.insee_code}-${item.section ?? ""}`} type="button"
                    className="flex w-full items-center justify-between px-4 py-3 text-left text-sm hover:bg-emerald-50"
                    onClick={() => choosePlace(item)}>
                    <span>{item.label}{item.section ? ` · section ${item.section}` : ""}</span>
                    <span className="ml-4 text-xs text-slate-500">{item.code_postal ?? item.insee_code}</span>
                  </button>
                ))}
              </div>
            )}
            {banPlaces.length > 1 && (
              <div className="absolute left-0 right-24 top-12 z-20 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl">
                {banPlaces.map((item) => (
                  <button key={`${item.insee_code}-${item.label}`} type="button"
                    className="block w-full px-4 py-3 text-left text-sm hover:bg-emerald-50"
                    onClick={() => choosePlace(item)}>{item.label}</button>
                ))}
              </div>
            )}
          </form>
        </div>
      </header>

      <div className="mx-auto max-w-[1480px] px-5 pb-14 pt-8 lg:px-10">
        <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-emerald-800">Transactions immobilières · DGFiP</p>
            <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Rechercher une vente immobilière</h1>
            <p className="mt-2 text-sm text-slate-500">Parcourez les ventes publiées par année, territoire, prix, surface et type de bien.</p>
            {availableYears.length > 0 && <p className="mt-2 text-xs text-slate-500">Années consultables actuellement : {availableYears.at(-1)}–{availableYears[0]} ({availableYears.length} millésimes). Les archives antérieures ne sont pas encore présentes sur l’hôte public.</p>}
          </div>
          <div className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm text-slate-600">
            <span className={`mr-2 inline-block h-2 w-2 rounded-full ${loadState === "ready" ? "bg-emerald-500" : "bg-amber-500"}`} />
            {loadState === "ready" ? `Données du ${new Date(manifest?.generated_at ?? "").toLocaleDateString("fr-FR")}` : "Préparation des données"}
          </div>
        </div>

        {loadState !== "ready" && (
          <section aria-live="polite" className="mb-7 rounded-xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-950">
            <strong>{loadState === "loading" ? "Chargement des données" : "Données en préparation"}</strong>
            <p className="mt-1 text-amber-900/80">{loadState === "loading" ? "Vérification de la dernière publication." : loadMessage || "Aucune transaction n’est encore disponible."}</p>
          </section>
        )}

        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Indicateurs nationaux">
          {[
            ["Transactions", number(national?.transaction_count), "sur la période publiée"],
            ["Prix médian", euro(national?.median_price), year === "all" ? "choisissez une année" : "biens confondus"],
            ["Prix médian au m²", euro(national?.median_price_per_m2), year === "all" ? "choisissez une année" : "biens bâtis renseignés"],
            ["Surface médiane", national?.median_surface ? `${number(national.median_surface)} m²` : "—", year === "all" ? "choisissez une année" : "surface bâtie"],
          ].map(([label, value, note]) => (
            <article key={label} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-900/[0.02]">
              <p className="text-sm text-slate-500">{label}</p>
              <p className="mt-3 text-2xl font-semibold tracking-tight">{value}</p>
              <p className="mt-1 text-xs text-slate-400">{note}</p>
            </article>
          ))}
        </section>

        <section className="mt-7 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm shadow-slate-900/[0.02]">
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 px-5 py-4">
            <div>
              <p className="text-xs uppercase tracking-widest text-slate-400">Zone sélectionnée</p>
              <h2 className="mt-1 text-xl font-semibold">{placeLabel}</h2>
            </div>
            <label className="flex items-center gap-2 text-sm text-slate-500">Année
              <select value={year} onChange={(event) => { setYear(event.target.value); setPage(0); setSales([]); setQueryFiles([]); setQueryPredicate(""); setHasSearched(false); setSelectedSale(null); setResultCount(null); }} className="h-10 rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-800">
                <option value="all">Toutes</option>{availableYears.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </label>
            <div className="flex rounded-lg bg-slate-100 p-1" role="tablist" aria-label="Type de vue">
              <button role="tab" aria-selected={tab === "kpis"} onClick={() => setTab("kpis")}
                className={`rounded-md px-4 py-2 text-sm font-medium ${tab === "kpis" ? "bg-white text-emerald-950 shadow-sm" : "text-slate-500"}`}>Indicateurs</button>
              <button role="tab" aria-selected={tab === "details"} onClick={() => setTab("details")}
                className={`rounded-md px-4 py-2 text-sm font-medium ${tab === "details" ? "bg-white text-emerald-950 shadow-sm" : "text-slate-500"}`}>Transactions</button>
            </div>
          </div>

          {tab === "kpis" ? (
            <div>
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-3"><label className="sr-only" htmlFor="commune-filter">Filtrer les communes</label><input id="commune-filter" value={communeQuery} onChange={(event) => { setCommuneQuery(event.target.value); setCommunePage(0); }} placeholder="Filtrer une commune, un code postal ou INSEE…" className="h-10 min-w-[260px] rounded-md border border-slate-300 bg-white px-3 text-sm"/><p className="text-sm text-slate-500">{number(communeCount)} commune{communeCount === 1 ? "" : "s"}</p><div className="flex items-center gap-2"><label className="text-xs text-slate-500">Lignes<select value={communePageSize} onChange={(event) => { setCommunePageSize(Number(event.target.value)); setCommunePage(0); }} className="ml-1 h-9 rounded-md border border-slate-300 bg-white px-2"><option value={100}>100</option><option value={250}>250</option><option value={500}>500</option></select></label><button disabled={communePage === 0} onClick={() => setCommunePage((value) => Math.max(0, value - 1))} className="rounded border px-2 py-1 text-xs disabled:opacity-40">Précédent</button><span className="text-xs text-slate-500">Page {communePage + 1} / {Math.max(1, Math.ceil(communeCount / communePageSize))}</span><button disabled={(communePage + 1) * communePageSize >= communeCount} onClick={() => setCommunePage((value) => value + 1)} className="rounded border px-2 py-1 text-xs disabled:opacity-40">Suivante</button></div></div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] border-collapse text-left text-sm">
                <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                  <tr>{([{key:"commune", label:"Commune"},{key:"transaction_count",label:"Ventes"},{key:"median_price",label:"Prix médian"},{key:"median_price_per_m2",label:"€/m² médian"},{key:"median_surface",label:"Surface médiane"}] as Array<{key:KpiSort;label:string}>).map(({key,label}) => <th key={key} className="px-5 py-3 font-medium"><button onClick={() => setCommuneSort((current) => ({ column:key, direction:current.column === key && current.direction === "ASC" ? "DESC" : "ASC" }))}>{label}{communeSort.column === key ? (communeSort.direction === "ASC" ? " ↑" : " ↓") : ""}</button></th>)}<th className="px-5 py-3 font-medium">Fourchette €/m²</th><th className="px-5 py-3 font-medium">Explorer</th></tr>
                </thead>
                <tbody>
                  {visibleCommunes.map((item) => (
                    <tr key={`${item.insee_code}-${item.year}`} className="border-t border-slate-100 hover:bg-emerald-50/40">
                      <td className="px-5 py-3 font-medium">{item.commune}<span className="ml-2 text-xs font-normal text-slate-400">{item.code_postal ?? item.insee_code}</span></td>
                      <td className="px-5 py-3">{number(item.transaction_count)}</td>
                      <td className="px-5 py-3">{euro(item.median_price)}</td>
                      <td className="px-5 py-3">{euro(item.median_price_per_m2)}</td>
                      <td className="px-5 py-3">{item.median_surface ? `${number(item.median_surface)} m²` : "—"}</td>
                      <td className="px-5 py-3 text-slate-500">{euro(item.p25_price_per_m2)} – {euro(item.p75_price_per_m2)}</td>
                      <td className="px-5 py-3"><button onClick={() => { const found = places.find((candidate) => candidate.kind === "commune" && candidate.insee_code === item.insee_code); if (found) { choosePlace(found); setTab("details"); } }} className="font-medium text-emerald-900 underline underline-offset-2">Voir les ventes</button></td>
                    </tr>
                  ))}
                  {visibleCommunes.length === 0 && <tr><td colSpan={7} className="px-5 py-12 text-center text-slate-500">{loadState === "ready" ? "Aucune commune dans cette sélection." : "Les indicateurs apparaîtront dès que les données seront publiées."}</td></tr>}
                </tbody>
              </table>
            </div>
            </div>
          ) : (
            <div className="grid lg:grid-cols-[260px_minmax(0,1fr)]">
              <form className="space-y-4 border-b border-slate-200 bg-slate-50/70 p-5 lg:border-b-0 lg:border-r" onSubmit={(event) => { event.preventDefault(); const problem = validateFilters(filters); if (problem) { setDuckError(problem); return; } setDuckError(""); setAppliedFilters(filters); setPage(0); setTab("details"); void runDetailsQuery(0, filters); }}>
                <label className="block text-xs font-medium text-slate-600">Territoire<select value={place?.department ?? department} onChange={(event) => { clearPlace(); setDepartment(event.target.value); setFilter("department", event.target.value === "all" ? "" : event.target.value); }} className="mt-1 h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm"><option value="all">Toute la France</option>{Object.keys(manifest?.departments ?? {}).sort((a, b) => a.localeCompare(b, "fr", { numeric: true })).map((code) => <option key={code} value={code}>Département {code}</option>)}</select></label>
                <label className="block text-xs font-medium text-slate-600">Code postal exact<input inputMode="numeric" value={filters.postalCode} onChange={(event) => setFilter("postalCode", event.target.value)} className="mt-1 h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm" placeholder="Ex. 75011" /></label>
                <label className="block text-xs font-medium text-slate-600">Numéro ou voie<input value={filters.address} onChange={(event) => setFilter("address", event.target.value)} className="mt-1 h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm" placeholder="Ex. 12 rue de la Paix" /></label>
                <div><label className="mb-1 block text-xs font-medium text-slate-600">Date de mutation · du</label><input type="date" value={filters.from} onChange={(event) => setFilter("from", event.target.value)} className="h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm" /></div>
                <div><label className="mb-1 block text-xs font-medium text-slate-600">Au</label><input type="date" value={filters.to} onChange={(event) => setFilter("to", event.target.value)} className="h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm" /></div>
                <div className="grid grid-cols-2 gap-2"><label className="text-xs font-medium text-slate-600">Prix min. (€)<input inputMode="decimal" value={filters.minPrice} onChange={(event) => setFilter("minPrice", event.target.value)} className="mt-1 h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm" /></label><label className="text-xs font-medium text-slate-600">Prix max. (€)<input inputMode="decimal" value={filters.maxPrice} onChange={(event) => setFilter("maxPrice", event.target.value)} className="mt-1 h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm" /></label></div>
                <div className="grid grid-cols-2 gap-2"><label className="text-xs font-medium text-slate-600">Surface bâtie min. (m²)<input inputMode="decimal" value={filters.minSurface} onChange={(event) => setFilter("minSurface", event.target.value)} className="mt-1 h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm" /></label><label className="text-xs font-medium text-slate-600">Max. (m²)<input inputMode="decimal" value={filters.maxSurface} onChange={(event) => setFilter("maxSurface", event.target.value)} className="mt-1 h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm" /></label></div>
                <div className="grid grid-cols-2 gap-2"><label className="text-xs font-medium text-slate-600">Terrain min. (m²)<input inputMode="decimal" value={filters.minLand} onChange={(event) => setFilter("minLand", event.target.value)} className="mt-1 h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm" /></label><label className="text-xs font-medium text-slate-600">Max. (m²)<input inputMode="decimal" value={filters.maxLand} onChange={(event) => setFilter("maxLand", event.target.value)} className="mt-1 h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm" /></label></div>
                <label className="block text-xs font-medium text-slate-600">Pièces principales<select value={filters.rooms} onChange={(event) => setFilter("rooms", event.target.value)} className="mt-1 h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm"><option value="">Toutes</option>{[1, 2, 3, 4, 5, 6].map((count) => <option key={count} value={count}>{count}{count === 6 ? "+" : ""}</option>)}</select></label>
                <label className="block text-xs font-medium text-slate-600">Type de bien<select value={filters.localType} onChange={(event) => setFilter("localType", event.target.value)} className="mt-1 h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm"><option value="">Tous</option><option>Maison</option><option>Appartement</option><option>Dépendance</option><option>Local industriel, commercial ou assimilé</option></select></label>
                <label className="block text-xs font-medium text-slate-600">Nature de mutation<select value={filters.mutation} onChange={(event) => setFilter("mutation", event.target.value)} className="mt-1 h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm"><option value="">Toutes</option><option>Vente</option><option>Vente en l’état futur d’achèvement</option><option>Vente de terrain à bâtir</option><option>Adjudication</option><option>Expropriation</option><option>Échange</option></select></label>
                <div className="flex gap-2"><button disabled={querying} className="h-10 flex-1 rounded-md bg-emerald-950 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300" type="submit">{querying ? "Recherche…" : "Afficher les ventes"}</button><button type="button" onClick={() => { setFilters(EMPTY_FILTERS); setAppliedFilters(EMPTY_FILTERS); setPage(0); setResultCount(null); clearPlace(); }} className="h-10 rounded-md border border-slate-300 bg-white px-3 text-xs font-medium text-slate-700">Réinitialiser</button></div>
                <p className="text-xs leading-5 text-slate-500">La recherche nationale peut télécharger plusieurs fichiers Parquet. Choisir un département ou une commune réduit fortement le chargement.</p>
              </form>
              <div className="min-w-0 p-5">
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                  <p className="text-sm text-slate-600">{resultCount !== null ? `${number(resultCount)} vente${resultCount > 1 ? "s" : ""} · ${resultCount ? `${number(page * pageSize + 1)}–${number(Math.min((page + 1) * pageSize, resultCount))}` : "aucun résultat"}` : "Choisissez un territoire ou lancez une recherche nationale."}</p>
                  <div className="flex flex-wrap items-center gap-2"><div className="flex rounded-md border border-slate-200 bg-white p-1" aria-label="Affichage des résultats">{([['list','Liste'],['split','Côte à côte'],['map','Carte']] as Array<[ResultsView,string]>).map(([value,label]) => <button key={value} type="button" aria-pressed={resultsView === value} onClick={() => setResultsView(value)} className={`rounded px-2 py-1 text-xs ${resultsView === value ? "bg-emerald-950 text-white" : "text-slate-600"}`}>{label}</button>)}</div><label className="text-xs text-slate-500">Lignes<select value={pageSize} onChange={(event) => { const size = Number(event.target.value); setPageSize(size); setPage(0); void runDetailsQuery(0, appliedFilters, sort, size); }} className="ml-1 h-9 rounded-md border border-slate-300 bg-white px-2 text-xs text-slate-800"><option value={25}>25</option><option value={50}>50</option><option value={100}>100</option></select></label><button onClick={() => void exportCsv()} disabled={!sales.length || querying} className="rounded-md border border-slate-300 px-3 py-2 text-xs font-medium text-slate-700 disabled:opacity-40">Exporter tous les résultats CSV</button><button disabled={querying || page === 0} onClick={() => void runDetailsQuery(0, appliedFilters)} className="rounded-md border border-slate-300 px-3 py-2 text-xs font-medium text-slate-700 disabled:opacity-40">« Première</button><button disabled={querying || page === 0} onClick={() => void runDetailsQuery(page - 1, appliedFilters)} className="rounded-md border border-slate-300 px-3 py-2 text-xs font-medium text-slate-700 disabled:opacity-40">‹ Précédente</button><button disabled={querying || resultCount === null || (page + 1) * pageSize >= resultCount} onClick={() => void runDetailsQuery(page + 1, appliedFilters)} className="rounded-md border border-slate-300 px-3 py-2 text-xs font-medium text-slate-700 disabled:opacity-40">Suivante ›</button><button disabled={querying || resultCount === null || (page + 1) * pageSize >= resultCount} onClick={() => void runDetailsQuery(Math.max(0, Math.ceil((resultCount ?? 0) / pageSize) - 1), appliedFilters)} className="rounded-md border border-slate-300 px-3 py-2 text-xs font-medium text-slate-700 disabled:opacity-40">Dernière »</button></div>
                </div>
                {duckError && <p role="alert" className="mb-3 rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-800">{duckError}</p>}
                {Object.entries(appliedFilters).filter(([key, value]) => Boolean(value) && key !== "department").length > 0 && <div className="mb-3 flex flex-wrap gap-2" aria-label="Filtres actifs">{Object.entries(appliedFilters).filter(([key, value]) => Boolean(value) && key !== "department").map(([key, value]) => <button key={key} onClick={() => { const next = { ...appliedFilters, [key]: "" }; setAppliedFilters(next); setFilters((current) => ({ ...current, [key]: "" })); setPage(0); void runDetailsQuery(0, next); }} className="rounded-full border border-emerald-900/20 bg-emerald-50 px-3 py-1 text-xs text-emerald-950">{key}: {value} ×</button>)}</div>}
                {resultsView !== "map" && <div className="overflow-x-auto rounded-lg border border-slate-200">
                  <table className="w-full min-w-[1400px] text-left text-sm">
                    <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500"><tr>{SORT_COLUMNS.map(({ key, label }) => <th key={key} aria-sort={sort.column === key ? (sort.direction === "ASC" ? "ascending" : "descending") : "none"} className="px-3 py-3 font-medium"><button className="whitespace-nowrap" onClick={() => { const nextSort = { column: key, direction: sort.column === key && sort.direction === "ASC" ? "DESC" : "ASC" } as const; setSort(nextSort); setPage(0); void runDetailsQuery(0, appliedFilters, nextSort); }}>{label}{sort.column === key ? (sort.direction === "ASC" ? " ↑" : " ↓") : ""}</button></th>)}<th className="px-3 py-3 font-medium">Statut</th></tr></thead>
                    <tbody>{sales.map((sale, index) => <tr key={`${sale.mutation_key ?? "sale"}-${index}`} tabIndex={0} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setSelectedSale(sale); } }} onClick={() => setSelectedSale(sale)} className={`cursor-pointer border-t border-slate-100 ${selectedSale === sale ? "bg-emerald-50" : "hover:bg-slate-50"}`}><td className="px-3 py-3">{String(sale.date_mutation ?? "—")}</td><td className="px-3 py-3">{String(sale.commune ?? "—")}</td><td className="px-3 py-3">{String(sale.nature_mutation ?? "—")}</td><td className="px-3 py-3">{String(sale.type_local ?? "—")}</td><td className="px-3 py-3">{String(sale.nombre_pieces_principales ?? "—")}</td><td className="px-3 py-3">{sale.surface_reelle_bati ? `${number(sale.surface_reelle_bati)} m²` : "—"}</td><td className="px-3 py-3">{sale.surface_terrain ? `${number(sale.surface_terrain)} m²` : "—"}</td><td className="px-3 py-3">{euro(sale.price_per_m2)}</td><td className="px-3 py-3 font-medium">{euro(sale.valeur_fonciere)}</td><td className="px-3 py-3"><span className="rounded-full bg-slate-100 px-2 py-1 text-xs">{String(sale.flag ?? sale.status ?? "publiée")}</span></td></tr>)}
                      {!sales.length && <tr><td colSpan={10} className="px-3 py-12 text-center text-slate-500">Aucune transaction ne correspond aux filtres.</td></tr>}</tbody>
                  </table>
                </div>}
                {resultsView !== "list" && <div className="mt-5">
                  <div className="mb-2 flex items-end justify-between gap-3"><div><h3 className="font-semibold">Carte des mutations</h3><p className="mt-1 text-xs text-slate-500">Points géolocalisés et regroupés à mesure du zoom.</p></div><span className="text-xs text-slate-400">Fond © OpenStreetMap</span></div>
                  {sales.some((sale) => sale.latitude != null && sale.longitude != null && Number.isFinite(Number(sale.latitude)) && Number.isFinite(Number(sale.longitude))) ? <TransactionMap sales={sales} center={mapCenter} onSelect={selectSale} /> : <div className="grid min-h-64 place-items-center rounded-lg border border-dashed border-slate-300 bg-slate-50 px-5 text-center"><p className="max-w-lg text-sm text-slate-600">Les fichiers DVF disponibles ne fournissent pas ici de coordonnées de vente. La carte affichera des transactions seulement si une géolocalisation vérifiable est publiée pour celles-ci.</p></div>}
                </div>}
                {selectedSale && <article className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50/60 p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-wider text-emerald-900">Détail de la ligne DVF</p><h3 className="mt-1 text-lg font-semibold">{String(selectedSale.commune ?? "Commune non précisée")} · {String(selectedSale.date_mutation ?? "Date non précisée")}</h3></div><button onClick={() => { const url = new URL(window.location.href); url.searchParams.set("sale", String(selectedSale.mutation_key ?? "")); void navigator.clipboard?.writeText(url.toString()); }} className="rounded-md border border-emerald-800/20 bg-white px-3 py-2 text-xs font-medium">Copier le lien</button></div><dl className="mt-4 grid gap-x-5 gap-y-3 text-sm sm:grid-cols-2 lg:grid-cols-3">{([["Valeur foncière", euro(selectedSale.valeur_fonciere)], ["Nature", selectedSale.nature_mutation], ["Type de local", selectedSale.type_local], ["Pièces principales", selectedSale.nombre_pieces_principales], ["Surface bâtie", selectedSale.surface_reelle_bati ? `${number(selectedSale.surface_reelle_bati)} m²` : "—"], ["Surface terrain", selectedSale.surface_terrain ? `${number(selectedSale.surface_terrain)} m²` : "—"], ["Adresse publiée", [selectedSale.no_voie, selectedSale.btq, selectedSale.type_voie, selectedSale.voie].filter(Boolean).join(" ") || "Non renseignée"], ["Code postal / INSEE", `${String(selectedSale.code_postal ?? "—")} / ${String(selectedSale.insee_code ?? "—")}`], ["Parcelle", [selectedSale.prefixe_section, selectedSale.section, selectedSale.no_plan].filter(Boolean).join(" ") || "Non renseignée"]] as Array<[string, unknown]>).map(([label, value]) => <div key={label}><dt className="text-xs text-slate-500">{label}</dt><dd className="mt-0.5 font-medium">{String(value ?? "—")}</dd></div>)}</dl><p className="mt-3 text-xs text-slate-600">Une mutation peut apparaître sur plusieurs lignes lorsqu’elle porte sur plusieurs biens ou parcelles. Cette fiche décrit la ligne source sélectionnée.</p></article>}
              </div>
            </div>
          )}
        </section>

        {manifest && <section className="mt-7 rounded-xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-900/[0.02]">
          <details>
            <summary className="cursor-pointer list-none">
              <h2 className="text-lg font-semibold">Télécharger les données</h2>
              <p className="mt-1 text-sm text-slate-500">Sources DVF, indicateurs, transactions Parquet et historique des révisions.</p>
            </summary>
            <div className="mt-5 space-y-5">
              <p className="text-sm leading-6 text-slate-600">Source : <a className="underline" href="https://www.data.gouv.fr/datasets/demandes-de-valeurs-foncieres" target="_blank" rel="noreferrer">DGFiP — Demandes de valeurs foncières</a> · Licence Ouverte 2.0. Les fichiers téléchargeables restent soumis aux conditions de réutilisation de la source.</p>
              <div className="grid gap-5 md:grid-cols-2">
                <div>
                  <h3 className="text-sm font-semibold">Indicateurs et index de recherche</h3>
                  <ul className="mt-2 space-y-1 text-sm">{Object.entries(manifest.kpi_files ?? {}).sort(([a], [b]) => Number(b) - Number(a)).map(([sourceYear, path]) => <li key={`kpi-${sourceYear}`}><a className="text-emerald-900 underline" href={`/api/data/${path}`} download>Indicateurs {sourceYear} (.json.gz)</a></li>)}{Object.entries(manifest.search_files ?? {}).sort(([a], [b]) => Number(b) - Number(a)).map(([sourceYear, path]) => <li key={`search-${sourceYear}`}><a className="text-emerald-900 underline" href={`/api/data/${path}`} download>Index de recherche {sourceYear} (.json.gz)</a></li>)}</ul>
                </div>
                <div>
                  <h3 className="text-sm font-semibold">Historique des comparaisons</h3>
                  <ul className="mt-2 space-y-1 text-sm">{(manifest.row_history ?? []).map((path) => <li key={path}><a className="text-emerald-900 underline" href={`/api/data/${path}`} download>{path.replace("history/", "Historique ")} (.parquet)</a></li>)}{!(manifest.row_history ?? []).length && <li className="text-slate-500">Aucune révision comparée pour l’instant.</li>}</ul>
                </div>
              </div>
              <div>
                <h3 className="text-sm font-semibold">Publications conservées</h3>
                <div className="mt-2 space-y-2">{Object.entries(manifest.snapshot_history ?? {}).sort(([a], [b]) => Number(b) - Number(a)).map(([sourceYear, versions]) => <details key={sourceYear} className="rounded-lg border border-slate-200 px-3 py-2">
                  <summary className="cursor-pointer text-sm font-medium">Millésime {sourceYear} · {versions.length} version{versions.length > 1 ? "s" : ""}</summary>
                  <div className="mt-2 space-y-3">{[...versions].sort((a, b) => b.version - a.version).map((snapshot) => <div key={`${sourceYear}-${snapshot.version}`} className="rounded-md bg-slate-50 p-3 text-sm">
                    <p className="font-medium">Version {snapshot.version}</p>
                    {snapshot.raw_source && <p className="mt-1"><a className="text-emerald-900 underline" href={`/api/data/${snapshot.raw_source}`} download>Fichier source TXT compressé (.txt.gz)</a></p>}
                    <details className="mt-2"><summary className="cursor-pointer text-slate-600">Parquet par département ({Object.keys(snapshot.details).length})</summary><ul className="mt-1 grid gap-x-4 sm:grid-cols-3">{Object.entries(snapshot.details).sort(([a], [b]) => a.localeCompare(b, "fr")).map(([department, path]) => <li key={path}><a className="text-emerald-900 underline" href={`/api/data/${path}`} download>Département {department}</a></li>)}</ul></details>
                  </div>)}</div>
                </details>)}</div>
              </div>
            </div>
          </details>
        </section>}

        <footer className="mt-6 flex flex-wrap justify-between gap-3 text-xs leading-5 text-slate-500">
          <p>Source : <a className="underline decoration-slate-400 underline-offset-2 hover:text-emerald-900" href="https://www.data.gouv.fr/datasets/demandes-de-valeurs-foncieres" target="_blank" rel="noreferrer">DGFiP — Demandes de valeurs foncières</a>, Licence Ouverte 2.0.</p>
          <p>Traitement local dans le navigateur · Site non indexé · Respect des conditions de réutilisation DVF.</p>
        </footer>
      </div>
    </main>
  );
}
