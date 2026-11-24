import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(cleanup);

// Waiting for the tab bar means opening its groups one by one, which is slow when every test file has its own worker.
configure({ asyncUtilTimeout: 5000 });
