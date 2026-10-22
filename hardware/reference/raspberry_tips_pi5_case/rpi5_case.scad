// =============================================================================
// raspberry.tips - Gehaeuse fuer Raspberry Pi 5
// Variante A: Pi 5 + offizieller Active Cooler
// Variante B: Pi 5 + Active Cooler + M.2 HAT+ (16-mm-Spacer)
//
// Version 2.0 (2026-08-13)
// Buchsenpositionen aus RASPBERRY_PI_5_WITH_ACTIVE_COOLER.stl, Bauteile per
// Komponentenanalyse getrennt und ueber ihre realen Abmessungen identifiziert.
// ACHTUNG zur Vorgeschichte: In v1.0 stammten die Zahlen zwar aus dem offiziellen
// STEP, die ZUORDNUNG war aber geraten - micro-HDMI und die FPC-Stecker waren
// vertauscht. Eine Bounding-Box sagt, dass dort etwas ist, nicht was. Vor jedem
// Druck die Kontrollzeichnung fotos/render/pi5_portlage.png gegen ein echtes
// Board pruefen lassen.
// v1.2: SPIEGELUNG GEFIXT. Bis v1.1 lautete die Umrechnung x<-X, y<-Z, z<-Y -
// das Vertauschen zweier Achsen kehrt die Haendigkeit um und ist damit eine
// Spiegelung, kein Drehen. Der Pi haette umgedreht eingelegt werden muessen.
// Richtig ist y = 28 - Z, in OpenSCAD: rotate([90,0,0]) auf das Referenzmodell.
// Aufbauhoehen aus den offiziellen Zeichnungen:
//   datasheets.raspberrypi.com/rpi5/raspberry-pi-5-mechanical-drawing.pdf
//   datasheets.raspberrypi.com/cooling/raspberry-pi-active-cooler-mechanical-drawing.pdf
//
// Lizenz: CC-BY 4.0 - Eigenentwurf, kein Remix.
// OpenSCAD 2021.01 oder neuer. Alle Masse in mm.
//
// KOORDINATEN: Nullpunkt = Innenecke der Wanne. Die Platine liegt mit ihrer Ecke
// bei (pcb_x0, pcb_y0), z = 0 ist der Wannenboden aussen.
//   x  = Laengsrichtung (85 mm)
//   y  = Querrichtung (56 mm)
//   x = 85er Ende  -> Ethernet + 4x USB
//   y = 0          -> USB-C, micro-HDMI, FPC
//   y = 56er Ende  -> GPIO-Leiste + PCIe-FFC, bleibt geschlossen
//   x = 0          -> microSD
// =============================================================================

/* [Was drucken] */
part = "kalibrierung"; // [wanne, deckel, kalibrierung, portlehre, vorschau]
// A = nur Active Cooler, B = zusaetzlich M.2 HAT+
variante = "B"; // [A, B]

/* [Platine - offizielle Zeichnung] */
pcb_l     = 85.0;
pcb_w     = 56.0;
pcb_t     = 1.4;
loch_rand = 3.5;
loch_dx   = 58.0;
loch_dy   = 49.0;

/* [Aufbauhoehen] */
kuehler_h  = 13.7;  // Active Cooler ueber Platinenoberseite
hat_spacer = 16.0;  // mitgelieferte Spacer des M.2 HAT+
hat_pcb_t  = 1.4;
ssd_stapel = 3.0;   // M.2-Sockel + SSD ueber der HAT-Platine
unter_pcb  = 3.0;   // Luft unter der Platine
luft_oben  = 1.5;

/* [Buchsen-Ueberstand ueber die Platinenkante] */
// GEMESSEN an RASPBERRY_PI_5_WITH_ACTIVE_COOLER.stl. Der Innenraum muss diesen
// Ueberstand aufnehmen, sonst stossen die Buchsen beim senkrechten Einsetzen an
// die Wand oberhalb der Oeffnungen und die Platine laesst sich nicht einlegen.
// Genau daran ist v1.0 bis v1.5 gescheitert.
ueber_x1 = 3.9;   // USB-Stapel ragen ueber die 85er Kante (x = max)
ueber_x0 = 0.0;   // microSD-Schacht schliesst buendig ab
ueber_y0 = 1.2;   // USB-C und micro-HDMI ragen ueber die Kante y = 0
ueber_y1 = 0.0;   // GPIO-Seite schliesst buendig ab

/* [Gehaeuse] */
wand     = 2.4;
boden    = 2.0;
deckel_t = 2.0;
spiel    = 0.4;   // Spiel um die Platine
radius   = 4.0;   // Eckenradius aussen
falz_h   = 3.0;   // Tiefe des Deckelfalzes

/* [Dome und Rastung] */
// "zapfen"   = Zentrierstift, der in die Platinenbohrung greift. Braucht keine
//              Schrauben, die Platine kann nicht verrutschen. Standard.
// "schraube" = flacher Dom mit Pilotbohrung fuer M2.5-Blechschrauben.
dom_typ    = "zapfen"; // [zapfen, schraube]
boss_d     = 6.0;
zapfen_d   = 2.4;  // Platinenbohrung ist 2,7 - 0,3 Luft fuer Drucktoleranz
zapfen_h   = 2.0;
boss_pilot = 2.2;  // Pilotbohrung fuer M2.5-Blechschraube.
                   // 2,7 ist das Loch IN DER PLATINE - im Kunststoff reisst
                   // das Gewinde damit aus.
rastung = true;
rast_d  = 1.6;

/* [Durchbrueche] */
port_spiel = 0.5;   // allseitige Zugabe. Etwas grosszuegiger als frueher, weil
                    // die Buchsen jetzt hinter der Wand sitzen und Steckergehaeuse
                    // sonst am Rand der Oeffnung anstossen.
// FPC-Schlitze fuer Kamera/Display. Standardmaessig zu: bei Variante B laeuft
// das PCIe-Kabel innen, und ein offener Schlitz ist nur Staubeintrag.
fpc_schlitze = false;
sd_schlitz   = true;

/* [Luftfuehrung] */
boden_slots   = true;
deckel_grille = true;
wand_waben    = true;   // Wabenfeld in der geschlossenen GPIO-Wand
slot_b        = 3.0;
slot_abstand  = 6.0;
wabe_schl     = 5.0;    // Schluesselweite der Sechsecke
wabe_steg     = 1.8;    // Stegbreite zwischen den Waben

/* [Optik] */
port_eckradius = 1.0;   // Rundung der Port-Oeffnungen
blende_tief    = 0.8;   // Tiefe der Blende um die Portgruppe, 0 = aus
blende_rand    = 2.5;   // Ueberstand der Blende um die Oeffnungen
radius_aussen  = 4.0;   // Eckenradius aussen (war 3,0)

/* [Beschriftung] */
schrift         = "raspberry.tips";
schrift_font    = "Liberation Sans:style=Bold";
schrift_groesse = 5.5;
schrift_tief    = 0.6;

/* [Hidden] */
$fn = 48;
eps = 0.01;

// =============================================================================
// Buchsenmasse aus dem offiziellen Referenzmodell
// Bezug: Platinenecke = (0,0), z = 0 ist die Platinenoberseite.
// Format: [ von, bis, z_unten, z_oben, "Bezeichnung" ]
// =============================================================================

// KORRIGIERT 2026-08-13. Quelle jetzt: Bauteilerkennung per Komponentenanalyse
// an RASPBERRY_PI_5_WITH_ACTIVE_COOLER.stl, Bauteile ueber ihre Abmessungen
// identifiziert statt geraten. In v1.0 waren micro-HDMI und die FPC-Stecker
// vertauscht, weil ich die langen schmalen Koerper (3,3 x 15,9 mm) fuer HDMI
// gehalten hatte - das sind die Kamera-/Display-Stecker. micro-HDMI misst
// 6,5 x 3,5 mm. Kontrollzeichnung: fotos/render/pi5_portlage.png

// x = 85er Kante (die 56 mm breite Schmalseite)
ports_rechts = [
    // Beide USB-Stapel als eine Oeffnung: dazwischen liegen nur 2,8 mm.
    [ 22.30, 54.66, -3.50, 16.78, "4x USB (beide Stapel)" ],
    [  2.25, 18.15, -2.05, 13.70, "Ethernet RJ45" ]
];

// y = 0 (85 mm lange Seite mit Strom und Video)
ports_vorn = [
    [  6.73, 15.67, -0.80,  3.16, "USB-C Strom" ],
    [ 22.55, 29.05, -0.55,  2.97, "micro-HDMI 0" ],
    [ 35.95, 42.45, -0.55,  2.97, "micro-HDMI 1" ]
];

// optionale FPC-Schlitze auf derselben Kante
ports_fpc = [
    [ 47.40, 50.70,  0.00,  3.90, "FPC CAM/DISP 0" ],
    [ 53.60, 56.90,  0.00,  3.90, "FPC CAM/DISP 1" ]
];

// x = 0 (Schmalseite gegenueber USB)
ports_links = [
    [ 22.00, 33.95, -3.05, -1.60, "microSD" ]
];

// Position des Kuehlers: er sitzt auf dem Lochraster, also mittig darauf.
// Mitte des Rasters = (loch_rand + loch_dx/2, loch_rand + loch_dy/2)
kuehler_mx = loch_rand + loch_dx / 2;
kuehler_my = loch_rand + loch_dy / 2;

// --- abgeleitete Masse -------------------------------------------------------
stapel_h = (variante == "B")
    ? hat_spacer + hat_pcb_t + ssd_stapel
    : kuehler_h;

innen_h  = unter_pcb + pcb_t + stapel_h + luft_oben;
innen_l  = pcb_l + ueber_x0 + ueber_x1 + 2 * spiel;
innen_w  = pcb_w + ueber_y0 + ueber_y1 + 2 * spiel;
aussen_l = innen_l + 2 * wand;
aussen_w = innen_w + 2 * wand;
wanne_h  = boden + innen_h;

pcb_x0 = wand + spiel + ueber_x0;
pcb_y0 = wand + spiel + ueber_y0;
pcb_z_oben = boden + unter_pcb + pcb_t;   // z = 0 der Buchsentabelle

loch_pos = [
    [loch_rand,           loch_rand],
    [loch_rand + loch_dx, loch_rand],
    [loch_rand,           loch_rand + loch_dy],
    [loch_rand + loch_dx, loch_rand + loch_dy]
];

// =============================================================================
// Hilfsmodule
// =============================================================================

module box_r(l, w, h, r) {
    hull() {
        translate([r,     r,     0]) cylinder(h = h, r = r);
        translate([l - r, r,     0]) cylinder(h = h, r = r);
        translate([r,     w - r, 0]) cylinder(h = h, r = r);
        translate([l - r, w - r, 0]) cylinder(h = h, r = r);
    }
}

// Rechteck mit runden Ecken, 2D
module rrect(b, h, r) {
    hull() for (x = [r, b - r], y = [r, h - r]) translate([x, y]) circle(r = r, $fn = 24);
}

// Wabenfeld: versetzte Sechsecke, als Schneidkoerper entlang +z
module waben(bx, by, tiefe, schl = 5.0, steg = 1.8) {
    dx = schl + steg;
    dy = dx * 0.866;
    nx = floor(bx / dx);
    ny = floor(by / dy);
    for (j = [0 : max(ny - 1, 0)])
        for (i = [0 : max(nx - 1, 0)]) {
            px = i * dx + (j % 2) * dx / 2;
            py = j * dy;
            if (px + schl / 2 <= bx && py + schl / 2 <= by)
                translate([px, py, -eps])
                    rotate([0, 0, 30]) cylinder(h = tiefe + 2 * eps, d = schl, $fn = 6);
        }
}

module dome() {
    for (p = loch_pos)
        translate([pcb_x0 + p[0], pcb_y0 + p[1], boden - eps])
            if (dom_typ == "zapfen") {
                // Sockel plus Zentrierstift mit Fase, damit die Platine beim
                // Einlegen von selbst in die richtige Lage rutscht.
                cylinder(h = unter_pcb + eps, d = boss_d);
                translate([0, 0, unter_pcb]) {
                    cylinder(h = zapfen_h - 0.6, d = zapfen_d);
                    translate([0, 0, zapfen_h - 0.6])
                        cylinder(h = 0.6, d1 = zapfen_d, d2 = zapfen_d - 0.8);
                }
            } else {
                difference() {
                    cylinder(h = unter_pcb + eps, d = boss_d);
                    translate([0, 0, -1]) cylinder(h = unter_pcb + 3, d = boss_pilot);
                }
            }
}

// Port-Durchbrueche mit gerundeten Ecken. Bewusst als Hull aus vier Zylindern
// gebaut, deren Achse direkt in Schnittrichtung zeigt - verschachtelte rotate()
// auf ein 2D-Profil hatten in v1.3 Breite und Hoehe vertauscht.
function port_r(p) = min(port_eckradius,
                         (p[3] - p[2] + 2 * port_spiel) / 2 - 0.05,
                         (p[1] - p[0] + 2 * port_spiel) / 2 - 0.05);

// Achse entlang +x (schneidet die Waende bei x = 0 und x = max)
module schlitz_x(x_start, a0, a1, b0, b1, r, tiefe) {
    hull() for (a = [a0 + r, a1 - r], b = [b0 + r, b1 - r])
        translate([x_start, a, b]) rotate([0, 90, 0])
            cylinder(h = tiefe, r = r, $fn = 24);
}

// Achse entlang +y (schneidet die Waende bei y = 0 und y = max)
module schlitz_y(y_start, a0, a1, b0, b1, r, tiefe) {
    hull() for (a = [a0 + r, a1 - r], b = [b0 + r, b1 - r])
        translate([a, y_start, b]) rotate([-90, 0, 0])
            cylinder(h = tiefe, r = r, $fn = 24);
}

module cut_rechts(p) {
    schlitz_x(aussen_l - wand - eps,
              pcb_y0 + p[0] - port_spiel, pcb_y0 + p[1] + port_spiel,
              pcb_z_oben + p[2] - port_spiel, pcb_z_oben + p[3] + port_spiel,
              port_r(p), wand + 2 * eps);
}

module cut_links(p) {
    schlitz_x(-eps,
              pcb_y0 + p[0] - port_spiel, pcb_y0 + p[1] + port_spiel,
              pcb_z_oben + p[2] - port_spiel, pcb_z_oben + p[3] + port_spiel,
              port_r(p), wand + 2 * eps);
}

module cut_vorn(p) {
    schlitz_y(-eps,
              pcb_x0 + p[0] - port_spiel, pcb_x0 + p[1] + port_spiel,
              pcb_z_oben + p[2] - port_spiel, pcb_z_oben + p[3] + port_spiel,
              port_r(p), wand + 2 * eps);
}

// Flache Vertiefung um die Portgruppe
module port_blende() {
    if (blende_tief > 0)
        schlitz_y(-eps,
                  pcb_x0 + ports_vorn[0][0] - blende_rand,
                  pcb_x0 + ports_vorn[len(ports_vorn) - 1][1] + blende_rand,
                  pcb_z_oben + ports_vorn[0][2] - blende_rand,
                  pcb_z_oben + ports_vorn[1][3] + blende_rand,
                  2.0, blende_tief + eps);
}

module alle_durchbrueche() {
    port_blende();
    for (p = ports_rechts) cut_rechts(p);
    for (p = ports_vorn) cut_vorn(p);
    if (fpc_schlitze) for (p = ports_fpc) cut_vorn(p);
    if (sd_schlitz)   for (p = ports_links) cut_links(p);
}

// Bodenschlitze: Ansaugseite. Halten Abstand zu den Domen.
module boden_luft() {
    n = floor((innen_l - 24) / slot_abstand);
    laenge = innen_w - 20;
    for (i = [0 : n - 1])
        translate([wand + 14 + i * slot_abstand, wand + 10, -eps])
            linear_extrude(height = boden + 2 * eps)
                rrect(slot_b, laenge, slot_b / 2 - 0.01);
}

// Deckelgitter, mittig ueber dem Kuehler statt mittig im Deckel
module deckel_luft() {
    gx = pcb_x0 + kuehler_mx;
    gy = pcb_y0 + kuehler_my;
    bx = 48; by = 36;
    translate([gx - bx / 2, gy - by / 2, 0])
        waben(bx, by, deckel_t, wabe_schl, wabe_steg);
}

// Wabenfeld in der geschlossenen GPIO-Wand (y = 56). Sitzt zwischen Boden und
// Falz, damit weder Standfestigkeit noch Deckelrand geschwaecht werden.
module wand_luft() {
    z0 = boden + 3;
    z1 = wanne_h - falz_h - 3;
    bx = aussen_l - 34;
    bz = z1 - z0;
    dx = wabe_schl + wabe_steg;
    dz = dx * 0.866;
    nx = floor(bx / dx);
    nz = floor(bz / dz);
    if (bz > wabe_schl + 2)
        for (j = [0 : max(nz - 1, 0)])
            for (i = [0 : max(nx - 1, 0)]) {
                px = i * dx + (j % 2) * dx / 2;
                pz = j * dz;
                if (px + wabe_schl / 2 <= bx && pz + wabe_schl / 2 <= bz)
                    translate([17 + px, aussen_w - wand - eps, z0 + pz])
                        rotate([-90, 0, 0])
                            cylinder(h = wand + 2 * eps, d = wabe_schl, $fn = 6);
            }
}

// =============================================================================
// Wanne
// =============================================================================
module wanne() {
    difference() {
        box_r(aussen_l, aussen_w, wanne_h, radius);

        // Innenraum
        translate([wand, wand, boden])
            box_r(innen_l, innen_w, innen_h + 1, max(radius - wand, 0.6));

        // Deckelfalz: obere falz_h der Wand innen auf halbe Staerke abtragen
        translate([wand / 2, wand / 2, wanne_h - falz_h])
            box_r(aussen_l - wand, aussen_w - wand, falz_h + 1, radius);

        alle_durchbrueche();
        if (boden_slots) boden_luft();
        if (wand_waben) wand_luft();

        // Rastmulden
        if (rastung)
            for (x = [aussen_l * 0.3, aussen_l * 0.7]) {
                translate([x, wand / 2, wanne_h - falz_h / 2])
                    rotate([90, 0, 0]) cylinder(h = wand, d = rast_d, center = true);
                translate([x, aussen_w - wand / 2, wanne_h - falz_h / 2])
                    rotate([90, 0, 0]) cylinder(h = wand, d = rast_d, center = true);
            }
    }

    dome();
}

// =============================================================================
// Deckel
// =============================================================================
module deckel() {
    difference() {
        union() {
            box_r(aussen_l, aussen_w, deckel_t, radius);

            // Schuerze. Sie ragt bewusst ueberlappend in die Platte hinein -
            // beruehren sich beide nur flaechig, liefert OpenSCAD zwei getrennte
            // Koerper statt eines geschlossenen Volumens.
            translate([wand / 2 + 0.2, wand / 2 + 0.2, -(falz_h - 0.3)])
                difference() {
                    box_r(aussen_l - wand - 0.4, aussen_w - wand - 0.4,
                          falz_h - 0.3 + 0.6, radius);
                    translate([wand / 2, wand / 2, -1])
                        box_r(aussen_l - 2 * wand - 0.4, aussen_w - 2 * wand - 0.4,
                              falz_h + 2, max(radius - wand, 0.6));
                }

            if (rastung)
                for (x = [aussen_l * 0.3, aussen_l * 0.7]) {
                    translate([x, wand / 2 + 0.2, -(falz_h / 2)]) sphere(d = rast_d);
                    translate([x, aussen_w - wand / 2 - 0.2, -(falz_h / 2)])
                        sphere(d = rast_d);
                }
        }

        if (deckel_grille) deckel_luft();

        // Beschriftung, vertieft in die Deckeloberseite
        translate([aussen_l / 2, aussen_w - 7, deckel_t - schrift_tief])
            linear_extrude(height = schrift_tief + eps)
                text(schrift, size = schrift_groesse, font = schrift_font,
                     halign = "center", valign = "center");
    }
}

// =============================================================================
// Kalibrierstueck
// =============================================================================
// Schneidet die echte Ecke heraus, in der die USB-Kante auf die HDMI-Kante
// trifft: prueft in einem kurzen Druck Wandstaerke, Domhoehe, Pilotbohrung,
// Falztiefe und die Lage der teuersten Durchbrueche.
module kalibrierung() {
    breite = 42;
    tiefe  = 30;

    intersection() {
        wanne();
        translate([aussen_l - breite, -1, -1])
            cube([breite + 1, tiefe + 1, wanne_h + 2]);
    }

    // Schriftprobe daneben
    translate([aussen_l - breite, tiefe + 4, 0])
        difference() {
            cube([breite, 12, 2]);
            translate([breite / 2, 6, 2 - schrift_tief])
                linear_extrude(height = schrift_tief + eps)
                    text(schrift, size = schrift_groesse, font = schrift_font,
                         halign = "center", valign = "center");
        }
}

// =============================================================================
// Portlehre
// =============================================================================
// Nur der Wandstreifen der y=56-Kante mit USB-C und beiden micro-HDMI, inklusive
// eines Bodenstreifens als Standfuss. Zum Anhalten an den echten Pi, bevor ein
// grosses Teil gedruckt wird - prueft genau die Stelle, die in v1.0 falsch war.
module portlehre() {
    // 18 statt 10 mm tief: Die erste Fassung war 90,6 x 10 mm - ein langer
    // schmaler Streifen mit grossem Hebel und wenig Haftflaeche, der sich beim
    // Abkuehlen an den Enden von der Platte zieht. Mit 18 mm ist die Standflaeche
    // fast doppelt so gross und das Teil steht ausserdem stabiler beim Anhalten.
    tiefe = 18;
    intersection() {
        wanne();
        cube([aussen_l, tiefe, pcb_z_oben + 8]);
    }
}

// =============================================================================
// Ausgabe
// =============================================================================
if (part == "portlehre") {
    portlehre();
} else if (part == "wanne") {
    wanne();
} else if (part == "deckel") {
    // geflippt: Platte aufs Bett, Schuerze nach oben, Praegung auf dem Bett
    rotate([180, 0, 0]) translate([0, 0, -deckel_t]) deckel();
} else if (part == "kalibrierung") {
    kalibrierung();
} else if (part == "vorschau") {
    wanne();
    translate([0, 0, wanne_h + 6]) deckel();
} else {
    echo("Unbekannter Wert fuer part");
}

echo(str("Variante ", variante,
         " | aussen ", aussen_l, " x ", aussen_w, " x ", wanne_h + deckel_t,
         " mm | Innenhoehe ", innen_h, " | Stapel ", stapel_h));
