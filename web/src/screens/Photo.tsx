import { useState } from "react";
import type { PhotoLink } from "../api";

/** Photo from a presigned link, or a placeholder when the link is absent (wallet-id) or broken (upload never finished). */
export function Photo({ photo, alt, className = "thumb" }: { photo?: PhotoLink; alt: string; className?: string }) {
  const [failed, setFailed] = useState(false);
  if (!photo || failed) {
    return (
      <div className="thumb-placeholder" role="img" aria-label="No photo available">
        No photo
      </div>
    );
  }
  return <img className={className} src={photo.url} alt={alt} loading="lazy" onError={() => setFailed(true)} />;
}
