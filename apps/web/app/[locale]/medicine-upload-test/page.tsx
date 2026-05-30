"use client";

import { MedicinePhotoUpload } from "@/components/medicine";

/**
 * Dev/test route for MedicinePhotoUpload (GSSoC / manual QA).
 * Visit: http://localhost:3000/en/medicine-upload-test
 */
export default function MedicineUploadTestPage() {
  return (
    <div className="mx-auto min-h-screen max-w-md bg-slate-50 p-6">
      <h1 className="mb-2 text-xl font-bold text-slate-900">Medicine upload test</h1>
      <p className="mb-6 text-sm text-slate-600">
        Requires Cloudinary vars in <code className="text-xs">apps/web/.env.local</code>.
        Check the browser console for the returned URL.
      </p>
      <MedicinePhotoUpload
        label="Upload Medicine Photo"
        onUploadComplete={(url) => {
          console.log("[medicine-upload-test] Uploaded:", url);
          window.alert(`Upload OK:\n${url}`);
        }}
        onError={(error) => {
          console.error("[medicine-upload-test] Error:", error);
        }}
      />
    </div>
  );
}
