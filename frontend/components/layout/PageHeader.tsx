import { Box, Heading, Text } from "@/components/ui/primitives";
import sxStyles from "./PageHeader.sx.module.css";

export function PageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <Box className={["page-header", sxStyles.sx1].filter(Boolean).join(" ")} >
      <Box>
        <Heading as="h1" className={sxStyles.sx2}>{title}</Heading>
        <Text className={sxStyles.sx3}>{description}</Text>
      </Box>
      {action}
    </Box>
  );
}
