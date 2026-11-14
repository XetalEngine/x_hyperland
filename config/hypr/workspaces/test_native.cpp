// Read the production policy parser without a live compositor or user HOME.
#include <iostream>
#include "native.hpp"
int main(int argc,char** argv){
    if(argc<2)return 1;
    try{
        auto policies=WorkspaceRules::read(argv[1]);
        std::cout<<WorkspaceRules::needsControls(policies)<<'\n';
        for(int i=2;i<argc;++i){
            auto p=WorkspaceRules::forWorkspace(policies,std::stoll(argv[i]));
            std::cout<<p.layout<<' '<<p.controls<<'\n';
        }
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
}
