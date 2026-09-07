// LicenseHawk frontend config.
//
// After deploying the contract on GenLayer Studio (studionet), paste its
// address here or set VITE_CONTRACT_ADDRESS in the Vercel build environment.
//
//   CHAIN = "studio"    -> GenLayer Studio Network (studionet)
//   CHAIN = "simulator" -> localnet / simulator

export const CONTRACT_ADDRESS =
  import.meta.env.VITE_CONTRACT_ADDRESS || "0xA47edd22962bc74eE2f611f4318F175Ca0dBf94A";

export const CHAIN = import.meta.env.VITE_CHAIN || "studio";
