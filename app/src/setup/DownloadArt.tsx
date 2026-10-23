import { Laptop, Package } from "lucide-react";

/** A calm, looping picture of a file making its way in. */
export function DownloadArt({ paused }: { paused: boolean }) {
  return (
    <div className={`download-art${paused ? " paused" : ""}`} aria-hidden="true">
      <span className="art-node art-box">
        <Package />
      </span>
      <span className="art-packet p1" />
      <span className="art-packet p2" />
      <span className="art-packet p3" />
      <span className="art-node art-device">
        <Laptop />
      </span>
    </div>
  );
}
