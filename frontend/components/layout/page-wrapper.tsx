interface PageWrapperProps {
  title: string;
  description?: string;
  children: React.ReactNode;
}

export function PageWrapper({ title, description, children }: PageWrapperProps) {
  return (
    <div className="flex-1 overflow-auto p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        {description && (
          <p className="text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {children}
    </div>
  );
}
