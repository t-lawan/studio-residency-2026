/*

  Listens to:
    fan/1 ... fan/N              -> speed percentage (0-100), plain number as string
    wind/oscillation/1           -> oscillation value, plain number as string

  Requires the "MQTT" library (processing-mqtt by 256dpi / Joel Gaehwiler):
    Processing IDE > Sketch > Import Library > Manage Libraries... > search "MQTT" > Install

  SETUP:
    1. Edit BROKER below to point at your MQTT broker.
    2. Set NUM_FANS to 2 or 4 depending on how many are currently wired up.
    3. Run.

  If your ESP32s publish JSON instead of a plain number (e.g. {"speed":42.0}),
  see the comment inside parsePayload() for how to adapt it.
  ==========================================================================
*/

import mqtt.*;

// ---------------------------------------------------------------- CONFIG --
String BROKER   = "mqtt://192.168.0.100:1883"; // e.g. "mqtt://192.168.1.50:1883" or "mqtt://user:pass@host:1883"
int    NUM_FANS = 2;                             // set to 4 when the other two come online
String OSC_TOPIC = "wind/oscillation/1";
String FAN_SPEED_TOPIC = "fan/speed/";

int HISTORY_LEN = 220;      // samples kept per channel for the scope trace
float STALE_MS  = 5000;     // ms with no update before a channel shows OFFLINE

boolean DEMO_MODE     = false; // true = skip MQTT entirely, feed fake wandering data (test the visuals with no broker/hardware)
int     BOOT_TIMEOUT  = 6000;  // ms to wait for a real broker handshake before giving up and showing the dashboard anyway
int     RECONNECT_EVERY = 5000; // ms between reconnect attempts once the initial connect fails


//color connected_status_colour = color(0, 255, 70);
color connected_status_colour = color(0);
color success_status_colour = color(0, 255, 70);
color failed_status_colour = color(255, 60, 60);
color amber = color(255, 176, 0);

int xOffset = 14;
// ------------------------------------------------------------- RUNTIME ---
MQTTClient client;
boolean mqttConnected = false;

PFont fontBig, fontMed, fontSmall, fontSmallBold;

Channel[] fans;
Channel osc;

boolean booting = true;
ArrayList<String> bootLines = new ArrayList<String>();
int bootLineIndex = 0;
int bootCharIndex = 0;
int lastBootTick = 0;

float scanlineOffset = 0;
int lastGlitchTime = 0;
float glitchUntil = -1;

int startMillis;
int bootStartMillis;
int lastConnectAttempt = -999999;
float[] noiseOffsets;
long[] simDropUntil; // demo mode only: while millis() < this, that channel stops sending data

void setup() {
  size(1280, 800);
  surface.setTitle("WIND WIND WIND");
  frameRate(30);

  fontBig   = createFont("Monospaced.bold", 42, true);
  fontMed   = createFont("Monospaced.bold", 20, true);
  fontSmallBold = createFont("Monospaced.bold", 16, true);
  fontSmall = createFont("Monospaced", 16, true);

  fans = new Channel[NUM_FANS];
  for (int i = 0; i < NUM_FANS; i++) {
    fans[i] = new Channel(FAN_SPEED_TOPIC + (i + 1), HISTORY_LEN);
  }
  osc = new Channel(OSC_TOPIC, HISTORY_LEN);

  noiseOffsets = new float[NUM_FANS + 1];
  for (int i = 0; i < noiseOffsets.length; i++) noiseOffsets[i] = random(1000);
  simDropUntil = new long[NUM_FANS + 1];

  startMillis = millis();
  bootStartMillis = millis();

  buildBootSequence();

  if (DEMO_MODE) {
    mqttConnected = true; // demo mode pretends the link is up immediately
  } else {
    client = new MQTTClient(this);
    attemptConnect();
  }
}

// Wraps client.connect() in a try/catch so a dead/unreachable broker just
// logs a message instead of throwing a RuntimeException at the sketch.
void attemptConnect() {
  lastConnectAttempt = millis();
  try {
    client.connect(BROKER, "fan-mainframe-" + (int)random(100000));
    println("[MQTT] connect successful");
  } catch (Exception e) {
    println("[MQTT] connect attempt failed: " + e.getMessage());
    mqttConnected = false;
  }
}

void buildBootSequence() {
  bootLines.add("WIND WIND WIND");
  bootLines.add("WIFI.......... OK");
  bootLines.add("MOUNTING MQTT BROKER.......... " + BROKER);
  for (int i = 0; i < NUM_FANS; i++) {
    bootLines.add(FAN_SPEED_TOPIC + (i + 1) + "........ OK");
  }
  bootLines.add(OSC_TOPIC + "........ OK");
}

// --------------------------------------------------------- MQTT CALLBACKS -
void clientConnected() {
  mqttConnected = true;
  print("CLIENT CONNECTED");
  for (int i = 0; i < NUM_FANS; i++) {
    client.subscribe(FAN_SPEED_TOPIC + (i + 1));
  }
  client.subscribe(OSC_TOPIC);
}

void connectionLost() {
  mqttConnected = false;
}

void messageReceived(String topic, byte[] payload) {
  float val = parsePayload(payload);
    
  if (Float.isNaN(val)) return;
  if (topic.equals(OSC_TOPIC)) {
    osc.push(val);
    return;
  }
  for (int i = 0; i < NUM_FANS; i++) {
    if (topic.equals(FAN_SPEED_TOPIC + (i + 1))) {
      fans[i].push(val);
      return;
    }
  }
}

// Adjust this if your ESP32 sends JSON instead of a bare number.
// Example for {"speed": 42.0} payloads, replace the body with:
//   String s = new String(payload).trim();
//   int i = s.indexOf(':');
//   int j = s.indexOf('}');
//   return Float.parseFloat(s.substring(i + 1, j).replace("\"", "").trim());
float parsePayload(byte[] payload) {
  try {
    String s = new String(payload).trim();
    return Float.parseFloat(s);
  } catch (Exception e) {
    return Float.NaN;
  }
}

// -------------------------------------------------------------- CHANNEL --
class Channel {
  String label;
  float[] history;
  int head = 0;
  int filled = 0;
  float current = 0;
  int lastUpdate = -999999;

  Channel(String label, int len) {
    this.label = label;
    history = new float[len];
  }

  void push(float v) {
    current = v;
    history[head] = v;
    head = (head + 1) % history.length;
    filled = min(filled + 1, history.length);
    lastUpdate = millis();
  }

  boolean isStale() {
    return lastUpdate < 0 || (millis() - lastUpdate) > STALE_MS;
  }

  float sample(int back) {
    if (filled == 0) return 0;
    int idx = ((head - 1 - back) % history.length + history.length) % history.length;
    return history[idx];
  }
}

// ------------------------------------------------------------------ DRAW --
void draw() {
  background(255);

  if (DEMO_MODE) simulateDemoData();

  if (!DEMO_MODE && !mqttConnected && millis() - lastConnectAttempt > RECONNECT_EVERY) {
    attemptConnect();
  }

  if (booting) {
    drawBoot();
    // give up waiting on a real broker after BOOT_TIMEOUT and show the
    // dashboard anyway (channels will just read OFFLINE until data arrives)
    if (!DEMO_MODE && millis() - bootStartMillis > BOOT_TIMEOUT) {
      booting = false;
    }
    return;
  }

  drawHeader();
  drawChannels();
  drawFooter();
}

// Fake, smoothly-wandering values so the sketch is fully previewable with
// no broker and no hardware connected. Toggle DEMO_MODE off to go live.
// Also randomly simulates individual channels dropping out (no data for a
// while), so you can see the per-channel OFFLINE indicator do its job --
// this is the same code path a real dropped fan or wind sensor would hit.
void simulateDemoData() {
  float t = millis() / 1000.0;

  for (int i = 0; i < NUM_FANS; i++) {
    if (millis() > simDropUntil[i]) {
      float v = 50 + 45 * (noise(noiseOffsets[i] + t * 0.15) - 0.5) * 2;
      fans[i].push(constrain(v, 0, 100));
      // small chance per frame to start a simulated dropout
      if (random(1) < 0.0008) {
        simDropUntil[i] = millis() + (long) random(4000, 12000);
      }
    }
  }

  int oi = NUM_FANS;
  if (millis() > simDropUntil[oi]) {
    float ov = 50 + 45 * (noise(noiseOffsets[oi] + t * 0.2) - 0.5) * 2;
    osc.push(constrain(ov, 0, 100));
    if (random(1) < 0.0008) {
      simDropUntil[oi] = millis() + (long) random(4000, 12000);
    }
  }
}

// --------------------------------------------------------------- HEADER --
void drawHeader() {
  pushStyle();
  stroke(connected_status_colour);
  noFill();

  fill(connected_status_colour);
  textFont(fontSmallBold);
  textAlign(LEFT, CENTER);
  int tX = 40;
  int tY = 40;
  for(int i = 0; i < NUM_FANS; i++) {
    text("WIND", tX + (5 * i), tY + (5 * i));
  }
  //text("WIND", 40, 65);
  //text("WIND", 45, 70);
  //text("WIND", 50, 75);

  textFont(fontSmallBold);
  textAlign(RIGHT, CENTER);
  String status = mqttConnected ? "LINK: ONLINE" : "LINK: SEARCHING...";
  color statusColor = mqttConnected ? connected_status_colour : failed_status_colour;
  fill(statusColor);
  text(status, width - 40, 40);

  int onlineCount = 0;
  for (int i = 0; i < NUM_FANS; i++) if (!fans[i].isStale()) onlineCount++;
  if (!osc.isStale()) onlineCount++;
  int totalChannels = NUM_FANS + 1;
  color countColor = (onlineCount == totalChannels) ? connected_status_colour : amber;
  fill(countColor);
  text("CHANNELS ONLINE: " + onlineCount + "/" + totalChannels, width - 40, 65);

  fill(connected_status_colour);
  int uptime = (millis() - startMillis) / 1000;
  text(String.format("UPTIME %02d:%02d:%02d", uptime / 3600, (uptime / 60) % 60, uptime % 60), width - 40, 90);
  popStyle();
}

// ------------------------------------------------------------- CHANNELS --
void drawChannels() {
  int top = 130;
  int bottom = height - 90;
  int cols = NUM_FANS <= 2 ? NUM_FANS : 2;
  int rows = ceil(NUM_FANS / (float) cols);

  int gap = 20;
  int panelW = (width - 40 - gap * (cols - 1)) / cols;
  int panelH = (bottom - top - gap * rows - 160) / max(rows, 1); // leave room for osc panel

  for (int i = 0; i < NUM_FANS; i++) {
    int col = i % cols;
    int row = i / cols;
    int x = 20 + col * (panelW + gap);
    int y = top + row * (panelH + gap);
    drawFanPanel(fans[i], x, y, panelW, panelH);
  }

  int oscY = top + rows * (panelH + gap);
  drawOscPanel(osc, 20, oscY, width - 40, 150);
}

void drawFanPanel(Channel ch, int x, int y, int w, int h) {
  boolean stale = ch.isStale();
  color primary = stale ? failed_status_colour : connected_status_colour;

  pushStyle();

  fill(connected_status_colour);
  textFont(fontSmallBold);
  textAlign(LEFT, TOP);
  text("[" +ch.label + "]", x + xOffset, y + 10);

  fill(stale ? failed_status_colour : success_status_colour);
  textAlign(RIGHT, TOP);
  text(stale ? "OFFLINE" : "LIVE", x + w - xOffset, y + 12);

  // big numeric readout
  fill(primary);
  textFont(fontSmall);
  textAlign(LEFT, TOP);
  String valStr = stale ? "--.-" : nf(ch.current, 0, 1);
  text(valStr + "%", x + xOffset, y + 40);

  // gauge bar
  int barX = x + xOffset;
  int barY = y + h - 46;
  int barW = w - 28;
  int barH = 6;
  
  float pct = constrain(ch.current, 0, 100) / 100.0;
  noStroke();
  fill(primary);
  rect(barX + 2, barY + 2, (barW - 4) * pct, barH - 4);

  // scope trace
  drawTrace(ch, x + xOffset, y + 90, w - 28, h - 150, primary);

  popStyle();
}

void drawOscPanel(Channel ch, int x, int y, int w, int h) {
  boolean stale = ch.isStale();
  color primary = stale ? failed_status_colour : connected_status_colour; // amber for the oscillation channel

  pushStyle();

  fill(primary);
  textFont(fontSmallBold);
  textAlign(LEFT, TOP);
  text("[" +ch.label + "]", x + xOffset, y + 10);

  fill(stale ? failed_status_colour : success_status_colour);
  textAlign(RIGHT, TOP);
  text(stale ? "OFFLINE" : "LIVE", x + w - xOffset, y + 12);

  fill(primary);
  textFont(fontSmall);
  textAlign(LEFT, TOP);
  String valStr = stale ? "--.-" : nf(ch.current, 0, 1);
  text(valStr, x + xOffset, y + 38);

  drawTrace(ch, x + 200, y + 44, w - 220, h - 60, primary);
  popStyle();
}

void drawTrace(Channel ch, int x, int y, int w, int h, color c) {
  pushStyle();

  int n = min(ch.filled, w);
  if (n > 1) {
    // glow pass
    strokeWeight(4);
    stroke(c, 50);
    drawTraceLine(ch, x, y, w, h, n);
    // sharp pass
    strokeWeight(1.2);
    stroke(c, 230);
    drawTraceLine(ch, x, y, w, h, n);
  }
  popStyle();
}

void drawTraceLine(Channel ch, int x, int y, int w, int h, int n) {
  beginShape();
  noFill();
  for (int i = 0; i < n; i++) {
    float v = ch.sample(n - 1 - i);
    float px = x + map(i, 0, n - 1, 0, w);
    float py = y + h - (constrain(v, 0, 100) / 100.0) * h;
    vertex(px, py);
  }
  endShape();
}

// -------------------------------------------------------------- FOOTER ---
void drawFooter() {
  pushStyle();
  stroke(connected_status_colour, 120);
  line(20, height - 50, width - 20, height - 50);

  fill(connected_status_colour);
  textFont(fontSmallBold);
  textAlign(LEFT, CENTER);
  text("CHANNELS: " + NUM_FANS + " FAN + 1 OSC   ::   BROKER " + BROKER, 20, height - 30);

  textAlign(RIGHT, CENTER);
  text("[ESC] QUIT", width - 20, height - 30);
  popStyle();
}

// ---------------------------------------------------------------- BOOT ---
void drawBoot() {
  fill(connected_status_colour);
  textFont(fontMed);
  textAlign(LEFT, TOP);

  int lineHeight = 30;
  int startY = height / 2 - (bootLines.size() * lineHeight) / 2;

  for (int i = 0; i < bootLineIndex; i++) {
    text(bootLines.get(i), 60, startY + i * lineHeight);
  }

  if (bootLineIndex < bootLines.size()) {
    String full = bootLines.get(bootLineIndex);
    String shown = full.substring(0, min(bootCharIndex, full.length()));
    text(shown, 60, startY + bootLineIndex * lineHeight);

    if (millis() - lastBootTick > 12) {
      bootCharIndex++;
      lastBootTick = millis();
      if (bootCharIndex > full.length()) {
        bootCharIndex = 0;
        bootLineIndex++;
      }
    }
  } else if (mqttConnected) {
    text("MQTT CONNECTED", 60, startY + bootLines.size() * lineHeight);
    if (millis() - lastBootTick > 600) {
      booting = false;
    }
  } else {
    // blinking cursor while waiting for broker
    if ((millis() / 400) % 2 == 0) {
      text("_", 60, startY + bootLines.size() * lineHeight);
    }
  }
}


void keyPressed() {
  if (key == ESC) {
    exit();
  }
}