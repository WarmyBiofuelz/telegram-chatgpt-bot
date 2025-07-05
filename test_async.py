import asyncio

async def test_function():
    print("Async function works!")
    await asyncio.sleep(1)
    print("Async sleep completed!")

if __name__ == "__main__":
    try:
        asyncio.run(test_function())
        print("✅ asyncio.run() works fine!")
    except RuntimeError as e:
        print(f"❌ asyncio.run() failed: {e}")
        print("This confirms the environment has an existing event loop") 