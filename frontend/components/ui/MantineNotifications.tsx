"use client";

import { Notifications } from "@mantine/notifications";

export function MantineNotifications() {
  return <Notifications
    position="top-center"
    limit={3}
    autoClose={4000}
    containerWidth={360}
    transitionDuration={180}
  />;
}
