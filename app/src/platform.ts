/** True when running in a Windows WebView (WebView2's user agent names Windows). */
export function isWindows(): boolean {
  return typeof navigator !== "undefined" && /Windows/i.test(navigator.userAgent);
}
