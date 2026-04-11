(function (window) {
    'use strict';

    const WAYPOINT_POINT_MIN_ZOOM = 6;
    const WAYPOINT_LABEL_MIN_ZOOM = 8;

    const routeColorPalette = [
        '#f87171', '#38bdf8', '#34d399', '#fbbf24', '#a78bfa',
        '#fb7185', '#06b6d4', '#84cc16', '#f59e0b', '#8b5cf6',
    ];
    const fixedGroupColors = {
        EMEA: '#8b5cf6',
        AMAS: '#0ea5e9',
        APAC: '#22c55e',
        NAM:  '#f59e0b',
        LATAM: '#a855f7',
        OCA:  '#e11d48',
    };
    const groupColorMap = new Map();

    function getRouteColor(group) {
        const key = (group || '').trim().toUpperCase() || '__UNGROUPED__';
        if (fixedGroupColors[key]) return fixedGroupColors[key];
        if (!groupColorMap.has(key)) {
            groupColorMap.set(key, routeColorPalette[groupColorMap.size % routeColorPalette.length]);
        }
        return groupColorMap.get(key);
    }

    function tileUrlForTheme(theme) {
        return theme === 'dark'
            ? 'https://{a-c}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png'
            : 'https://{a-c}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png';
    }

    function waypointPaletteForTheme(theme) {
        return theme === 'dark'
            ? { point: '#ffffff', text: '#ffffff', textStroke: '#000000' }
            : { point: '#0f172a', text: '#111827', textStroke: '#ffffff' };
    }

    function createWaypointPointStyle(palette) {
        return new ol.style.Style({
            image: new ol.style.Circle({
                radius: 1,
                fill: new ol.style.Fill({ color: palette.point }),
                stroke: new ol.style.Stroke({ color: palette.point, width: 1 }),
                opacity: 0.8,
            }),
        });
    }

    /**
     * Creates all common OpenLayers layers, sources, and utility functions.
     *
     * @param {object} opts
     * @param {string} opts.mapTarget     - DOM element id for the OL map
     * @param {string} opts.waypointsUrl  - Base URL for the waypoints GeoJSON endpoint
     * @param {string} opts.initialTheme  - 'light' | 'dark'
     *
     * @returns {{
     *   map, baseLayer,
     *   allWaypointsSource, allWaypointsLayer, allWaypointsLabelLayer,
     *   routeLineSource,
     *   waypointSource, waypointLayer,
     *   loadVisibleWaypoints,
     *   addWaypoint,
     *   refreshMapSize,
     * }}
     */
    function createBaseMapKit({ mapTarget, waypointsUrl, highlightedWaypointsUrl, initialTheme }) {
        let waypointPalette = waypointPaletteForTheme(initialTheme);
        let allWaypointsPointStyle = createWaypointPointStyle(waypointPalette);
        const waypointLabelStyleCache = new Map();

        function getWaypointLabelStyle(identifier) {
            let style = waypointLabelStyleCache.get(identifier);
            if (style) return style;
            style = new ol.style.Style({
                text: new ol.style.Text({
                    text: identifier,
                    offsetY: -6,
                    fill: new ol.style.Fill({ color: waypointPalette.text }),
                    font: 'bold 9px monospace',
                    stroke: new ol.style.Stroke({ color: waypointPalette.textStroke, width: 1, opacity: 0.9 }),
                }),
            });
            waypointLabelStyleCache.set(identifier, style);
            return style;
        }

        const baseLayer = new ol.layer.Tile({
            source: new ol.source.XYZ({ url: tileUrlForTheme(initialTheme) }),
        });

        const map = new ol.Map({
            target: mapTarget,
            layers: [baseLayer],
            view: new ol.View({
                center: ol.proj.fromLonLat([-30, 40]),
                zoom: 1,
            }),
        });

        let allWaypointsSource = new ol.source.Vector();
        let waypointFetchController = null;

        const allWaypointsLayer = new ol.layer.Vector({
            source: allWaypointsSource,
            zIndex: 8,
            style: allWaypointsPointStyle,
        });

        const allWaypointsLabelLayer = new ol.layer.Vector({
            source: allWaypointsSource,
            declutter: true,
            zIndex: 9,
            style: function (feature) {
                const identifier = feature.get('identifier');
                if (!identifier) return null;
                return getWaypointLabelStyle(identifier);
            },
        });

        map.addLayer(allWaypointsLayer);
        map.addLayer(allWaypointsLabelLayer);

        const routeLineSource = new ol.source.Vector();

        const highlightedWaypointsSource = new ol.source.Vector();
        const highlightedWaypointsLayer = new ol.layer.Vector({
            source: highlightedWaypointsSource,
            zIndex: 12,
            style: function (feature) {
                const color = feature.get('color') || '#f97316';
                const identifier = feature.get('identifier');
                return new ol.style.Style({
                    image: new ol.style.Circle({
                        radius: 5,
                        fill: new ol.style.Fill({ color: color }),
                        stroke: new ol.style.Stroke({ color: '#ffffff', width: 1.5 }),
                    }),
                    text: new ol.style.Text({
                        text: identifier,
                        offsetY: -12,
                        fill: new ol.style.Fill({ color: color }),
                        font: 'bold 11px monospace',
                        stroke: new ol.style.Stroke({ color: '#000000', width: 2 }),
                    }),
                });
            },
        });
        map.addLayer(highlightedWaypointsLayer);

        function loadHighlightedWaypoints() {
            if (!highlightedWaypointsUrl) return;
            fetch(highlightedWaypointsUrl)
                .then(r => r.json())
                .then(data => {
                    const features = new ol.format.GeoJSON().readFeatures(data, { featureProjection: 'EPSG:3857' });
                    highlightedWaypointsSource.clear();
                    highlightedWaypointsSource.addFeatures(features);
                })
                .catch(() => {});
        }

        var highlightedToggle = document.getElementById('toggle-highlighted-waypoints');
        if (highlightedToggle) {
            highlightedToggle.addEventListener('change', function () {
                highlightedWaypointsLayer.setVisible(this.checked);
                map.render();
            });
        }

        loadHighlightedWaypoints();

        const waypointSource = new ol.source.Vector();
        const waypointLayer = new ol.layer.Vector({ source: waypointSource, zIndex: 11 });
        map.addLayer(waypointLayer);

        function loadVisibleWaypoints() {
            if (waypointFetchController) waypointFetchController.abort();

            const toggleEl = document.getElementById('toggle-waypoints');
            const enabled = toggleEl ? toggleEl.checked : false;
            const zoom = map.getView().getZoom() || 0;
            const showPoints = enabled && zoom >= WAYPOINT_POINT_MIN_ZOOM;
            const showLabels = enabled && zoom >= WAYPOINT_LABEL_MIN_ZOOM;

            allWaypointsLayer.setVisible(showPoints);
            allWaypointsLabelLayer.setVisible(showLabels);

            if (!showPoints) {
                allWaypointsSource.clear();
                return;
            }

            const extent = map.getView().calculateExtent(map.getSize());
            const [minX, minY, maxX, maxY] = extent;
            const [minLon, minLat] = ol.proj.toLonLat([minX, minY]);
            const [maxLon, maxLat] = ol.proj.toLonLat([maxX, maxY]);

            waypointFetchController = new AbortController();
            fetch(
                `${waypointsUrl}?minLon=${minLon}&minLat=${minLat}&maxLon=${maxLon}&maxLat=${maxLat}`,
                { signal: waypointFetchController.signal }
            )
                .then(r => r.json())
                .then(data => {
                    const features = new ol.format.GeoJSON().readFeatures(data, { featureProjection: 'EPSG:3857' });
                    allWaypointsSource.clear();
                    allWaypointsSource.addFeatures(features);
                })
                .catch(() => {});
        }

        function addWaypoint(lon, lat, name) {
            const feature = new ol.Feature({
                geometry: new ol.geom.Point(ol.proj.fromLonLat([lon, lat])),
                name: name,
            });
            feature.setStyle(new ol.style.Style({
                image: new ol.style.Circle({
                    radius: 3,
                    fill: new ol.style.Fill({ color: 'white' }),
                    stroke: new ol.style.Stroke({ color: 'white', width: 1 }),
                }),
                text: new ol.style.Text({
                    text: name,
                    offsetY: -8,
                    fill: new ol.style.Fill({ color: '#fff' }),
                    font: 'bold 9px monospace',
                    stroke: new ol.style.Stroke({ color: '#000', width: 1, opacity: 0.7 }),
                }),
            }));
            waypointSource.addFeature(feature);
        }

        function refreshMapSize() {
            requestAnimationFrame(function () {
                map.updateSize();
                setTimeout(function () { map.updateSize(); }, 120);
            });
        }

        var waypointsToggle = document.getElementById('toggle-waypoints');
        if (waypointsToggle) {
            waypointsToggle.addEventListener('change', loadVisibleWaypoints);
        }

        map.on('moveend', loadVisibleWaypoints);

        window.addEventListener('themechange', function (event) {
            var theme = (event.detail && event.detail.theme) ? event.detail.theme : 'light';
            waypointPalette = waypointPaletteForTheme(theme);
            allWaypointsPointStyle = createWaypointPointStyle(waypointPalette);
            waypointLabelStyleCache.clear();
            baseLayer.setSource(new ol.source.XYZ({ url: tileUrlForTheme(theme) }));
            allWaypointsLayer.setStyle(allWaypointsPointStyle);
            allWaypointsLayer.changed();
            allWaypointsLabelLayer.changed();
        });

        window.addEventListener('resize', refreshMapSize);

        loadVisibleWaypoints();
        refreshMapSize();

        return {
            map,
            baseLayer,
            allWaypointsSource,
            allWaypointsLayer,
            allWaypointsLabelLayer,
            routeLineSource,
            highlightedWaypointsSource,
            highlightedWaypointsLayer,
            loadHighlightedWaypoints,
            waypointSource,
            waypointLayer,
            loadVisibleWaypoints,
            addWaypoint,
            refreshMapSize,
        };
    }

    function OverlayLayer(map) {
        const source = new ol.source.Vector({
            format: new ol.format.GeoJSON(),
        });

        const layer = new ol.layer.Vector({
            source: source,
            style: new ol.style.Style({
                stroke: new ol.style.Stroke({
                    color: '#00ffcc',
                    width: 0.1,
                    opacity: 0.5,
                }),
            }),
            zIndex: 6,
        });

        const labelLayer = new ol.layer.Vector({
            source: source,
            declutter: true,
            zIndex: 7,
            style: function(feature) {
                const props = feature.getProperties();
                const identifier = props.label || props.name || props.id || props.ID;
                if (!identifier) return null;

                let lon = props.label_lon || props.lon || props.LON;
                let lat = props.label_lat || props.lat || props.LAT;

                if (!lon || !lat) {
                    const geometry = feature.getGeometry();
                    if (geometry) {
                        const extent = geometry.getExtent();
                        const centerX = extent[0] + (extent[2] - extent[0]) / 2;
                        const centerY = extent[1] + (extent[3] - extent[1]) / 2;
                        const viewProjection = map.getView().getProjection();
                        const lonLatCoords = ol.proj.transform([centerX, centerY], viewProjection, 'EPSG:4326');
                        lon = lonLatCoords[0];
                        lat = lonLatCoords[1];
                    }
                }

                if (!lon || !lat) return null;

                return new ol.style.Style({
                    geometry: new ol.geom.Point(ol.proj.fromLonLat([parseFloat(lon), parseFloat(lat)])),
                    text: new ol.style.Text({
                        text: String(identifier),
                        font: 'bold 10px monospace',
                        fill: new ol.style.Fill({ color: 'rgba(0, 255, 204, 0.6)' }),
                        stroke: new ol.style.Stroke({ color: 'rgba(0, 0, 0, 0.45)', width: 1 }),
                        textAlign: 'center',
                    }),
                });
            },
        });

        map.addLayer(layer);
        map.addLayer(labelLayer);
        layer.setVisible(false);
        labelLayer.setVisible(false);

        let currentUrl = null;

        return {
            setUrl: function(url) {
                if (!url) {
                    source.setUrl('');
                    source.clear(true);
                    layer.setVisible(false);
                    labelLayer.setVisible(false);
                    currentUrl = null;
                    return;
                }
                source.setUrl(url);
                currentUrl = url;
                source.refresh();
                layer.setVisible(true);
                labelLayer.setVisible(true);
            },
            setVisible: function(visible) {
                layer.setVisible(visible);
                labelLayer.setVisible(visible);
            },
            clear: function() {
                source.setUrl('');
                source.clear(true);
                layer.setVisible(false);
                labelLayer.setVisible(false);
                currentUrl = null;
            },
            setUrlAndVisible: function(url) {
                if (!url) {
                    this.clear();
                    return;
                }
                source.setUrl(url);
                currentUrl = url;
                source.refresh();
                layer.setVisible(true);
                labelLayer.setVisible(true);
            },
            getLayer: function() {
                return layer;
            },
        };
    }

    window.MapShared = {
        WAYPOINT_POINT_MIN_ZOOM,
        WAYPOINT_LABEL_MIN_ZOOM,
        getRouteColor,
        tileUrlForTheme,
        waypointPaletteForTheme,
        createWaypointPointStyle,
        createBaseMapKit,
        OverlayLayer,
    };

}(window));
