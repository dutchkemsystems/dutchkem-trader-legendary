import type { WebSocketMessage } from "./types";
import { WS_BASE_URL, RECONNECT_INTERVAL, MAX_RECONNECT_ATTEMPTS } from "./constants";

export type WSEventHandler = (message: WebSocketMessage) => void;

export class WSClient {
  private ws: WebSocket | null = null;
  private url: string;
  private handlers: Map<string, WSEventHandler[]> = new Map();
  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private shouldReconnect = true;
  private channel: string;

  constructor(channel: string) {
    this.channel = channel;
    this.url = `${WS_BASE_URL}/${channel}`;
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) return;

    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.emit("open", { type: "open" });
    };

    this.ws.onmessage = (event) => {
      try {
        const message: WebSocketMessage = JSON.parse(event.data);
        this.emit(message.type, message);
        this.emit("*", message);
      } catch {
        // ignore malformed messages
      }
    };

    this.ws.onclose = () => {
      this.emit("close", { type: "close" });
      if (this.shouldReconnect) {
        this.scheduleReconnect();
      }
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  disconnect(): void {
    this.shouldReconnect = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }

  subscribe(event: string, handler: WSEventHandler): () => void {
    if (!this.handlers.has(event)) {
      this.handlers.set(event, []);
    }
    this.handlers.get(event)!.push(handler);

    return () => {
      const list = this.handlers.get(event);
      if (list) {
        const idx = list.indexOf(handler);
        if (idx !== -1) list.splice(idx, 1);
      }
    };
  }

  send(data: Record<string, unknown>): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  private emit(event: string, message: WebSocketMessage): void {
    const list = this.handlers.get(event);
    if (list) {
      for (const handler of list) {
        handler(message);
      }
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) return;

    this.reconnectTimer = setTimeout(() => {
      this.reconnectAttempts++;
      this.connect();
    }, RECONNECT_INTERVAL);
  }
}
