import JobSearch from "../../app/job/JobSearch";
import { Protected } from "../../app/job/components";
import { tr } from "../../app/job/i18n";

export default function SearchPage() {
  return <Protected title={tr("jobs")}>{() => <JobSearch />}</Protected>;
}
