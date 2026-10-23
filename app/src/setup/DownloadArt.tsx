/** A calm, looping picture of a file making its way in. CSS only. */
export function DownloadArt({ paused }: { paused: boolean }) {
  return (
    <div className={`download-art${paused ? " paused" : ""}`} aria-hidden="true">
      <span className="art-box" />
      <span className="art-packet p1" />
      <span className="art-packet p2" />
      <span className="art-packet p3" />
      <span className="art-device" />
    </div>
  );
}
