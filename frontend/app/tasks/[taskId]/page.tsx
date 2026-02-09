import type { Metadata } from "next";
import { TaskLiveView } from "../../../components/TaskLiveView";

interface TaskPageProps {
  params: Promise<{
    taskId: string;
  }>;
}

export const metadata: Metadata = {
  title: "任务详情 - OopsNote",
};

export default async function TaskPage({ params }: TaskPageProps) {
  const { taskId } = await params;
  return <TaskLiveView taskId={taskId} />;
}
