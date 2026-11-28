import { Icon, Menu, type MenuItem } from "../ui";

export function WorkspaceMenu({ items }: { items: MenuItem[] }) {
  return (
    <Menu
      label="More actions"
      trigger={<><span className="hidden sm:inline">More actions</span><Icon name="more" className="h-4 w-4" /></>}
      triggerTestId="more-actions-trigger"
      menuTestId="more-actions"
      menuClassName="w-64"
      items={items}
    />
  );
}
