from . import register

def main():
    class DummyCtx:
        def register_tool(self, **kwargs):
            print("Tool registered:", kwargs["name"])
        def __setattr__(self, k, v):
            print(f"Set plugin info: {k}={v}")
    ctx = DummyCtx()
    register(ctx)

if __name__ == "__main__":
    main()
