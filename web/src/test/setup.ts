import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

if (typeof window.PointerEvent === "undefined") {
  class PointerEventPolyfill extends MouseEvent {
    pointerId: number;
    pointerType: string;
    constructor(type: string, params: PointerEventInit = {}) {
      super(type, params);
      this.pointerId = params.pointerId ?? 1;
      this.pointerType = params.pointerType ?? "mouse";
    }
  }
  Object.defineProperty(window, "PointerEvent", { value: PointerEventPolyfill, writable: true });
  Object.defineProperty(globalThis, "PointerEvent", { value: PointerEventPolyfill, writable: true });
}

afterEach(() => {
  cleanup();
});

type DialogProto = { showModal?: () => void; close?: () => void };

const dialogProto = (
  typeof HTMLDialogElement !== "undefined"
    ? HTMLDialogElement.prototype
    : typeof HTMLUnknownElement !== "undefined"
      ? HTMLUnknownElement.prototype
      : null
) as unknown as DialogProto | null;

if (dialogProto && typeof dialogProto.showModal !== "function") {
  Object.defineProperty(dialogProto, "showModal", {
    configurable: true,
    writable: true,
    value(this: Element) {
      this.setAttribute("open", "");
    },
  });
  Object.defineProperty(dialogProto, "close", {
    configurable: true,
    writable: true,
    value(this: Element) {
      this.removeAttribute("open");
    },
  });
}

if (typeof HTMLMediaElement !== "undefined") {
  Object.defineProperty(HTMLMediaElement.prototype, "play", {
    configurable: true,
    writable: true,
    value: () => Promise.resolve(),
  });
  Object.defineProperty(HTMLMediaElement.prototype, "pause", {
    configurable: true,
    writable: true,
    value: () => {},
  });
}

if (typeof Element !== "undefined" && typeof Element.prototype.scrollIntoView !== "function") {
  Object.defineProperty(Element.prototype, "scrollIntoView", {
    configurable: true,
    writable: true,
    value: () => {},
  });
}
