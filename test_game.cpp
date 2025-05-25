// Test C++ file for repo-map
#include <vector>
#include <memory>
#include <string>

namespace Engine {
    class GameObject {
    private:
        std::string name;
        float x, y, z;
        
    public:
        GameObject(const std::string& name, float x = 0.0f, float y = 0.0f, float z = 0.0f);
        virtual ~GameObject() = default;
        
        virtual void update(float deltaTime) = 0;
        virtual void render() const;
        
        const std::string& getName() const { return name; }
        void setPosition(float x, float y, float z);
        std::tuple<float, float, float> getPosition() const;
    };

    class Player : public GameObject {
    private:
        int health;
        int score;
        
    public:
        Player(const std::string& name, float x, float y);
        
        void update(float deltaTime) override;
        void takeDamage(int damage);
        void addScore(int points);
        
        int getHealth() const { return health; }
        int getScore() const { return score; }
    };

    template<typename T>
    class ComponentManager {
    private:
        std::vector<std::unique_ptr<T>> components;
        
    public:
        void addComponent(std::unique_ptr<T> component);
        T* getComponent(size_t index);
        void removeComponent(size_t index);
        size_t getComponentCount() const;
    };

    struct Transform {
        float x, y, z;
        float rotX, rotY, rotZ;
        float scaleX, scaleY, scaleZ;
        
        Transform(float x = 0.0f, float y = 0.0f, float z = 0.0f);
        void translate(float dx, float dy, float dz);
        void rotate(float rx, float ry, float rz);
    };

    enum class EntityState {
        IDLE,
        MOVING,
        ATTACKING,
        DEAD
    };

    // Global functions
    void initializeEngine();
    void shutdownEngine();
    std::shared_ptr<GameObject> createGameObject(const std::string& type, const std::string& name);
    
    template<typename T>
    T* findComponent(const GameObject& obj);
}